import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, render_template, request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from db import Config, Event, get_engine, init_db, wait_for_db
from state import ThreadSafeState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)

STUB = os.environ.get("STUB_SENSORS", "").lower() in ("1", "true", "yes")
SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "/data/snapshots"))

# swap in fake sensors when running on dev pc without hardware
if STUB:
    from stubs import CameraThread, PIRThread, LEDController, Buzzer, DHTThread
    log.info("Stub sensors active (STUB_SENSORS=1)")
else:
    from camera import CameraThread
    from pir import PIRThread
    from leds import LEDController
    from buzzer import Buzzer
    from dht import DHTThread

from uploader import UploaderThread

app = Flask(__name__)

engine = get_engine()
wait_for_db(engine)
init_db(engine)

# load saved mode and schedule from DB so we restore state across restarts
with Session(engine) as _s:
    _mode = _s.get(Config, "current_mode").value
    _sched_start = _s.get(Config, "schedule_start").value
    _sched_end = _s.get(Config, "schedule_end").value
    _tz_row = _s.get(Config, "timezone")
    _tz_name = _tz_row.value if _tz_row else "Africa/Johannesburg"

TZ = ZoneInfo(_tz_name)

# HH:MM in 24h format, 00:00 - 23:59
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

state =ThreadSafeState(mode=_mode, schedule_start=_sched_start, schedule_end=_sched_end)
stop_event = threading.Event()

leds = LEDController()
buzzer = Buzzer()


def _apply_mode_leds(mode: str) -> None:
    # stealth and alert both keep green on as a "system active" indicator
    if mode in ("Stealth", "Alert"):
        leds.set_green(True)
        leds.set_red(False)
    else:  # Manual — tHe user controls leds from dashboard
        leds.set_green(False)
        leds.set_red(False)


_apply_mode_leds(_mode)


def _in_armed_hours() -> bool:

    # check if current local time falls inside the configured alert window
    snap = state.snapshot()
    now = datetime.now(TZ).time()
    start_t = dt_time.fromisoformat(snap["schedule_start"])
    end_t = dt_time.fromisoformat(snap["schedule_end"])
    # overnight window e.g. 22:00-06:00 wraps past midnight
    if start_t > end_t:
        return now >= start_t or now < end_t
    return start_t <= now < end_t


def _save_snapshot(ts: datetime, kind: str = "motion") -> int | None:
    frame = camera_thread.get_frame()
    if frame is None:
        log.warning("No camera frame available for snapshot")
        return None
    subdir = SNAPSHOT_DIR / ts.strftime("%Y/%m/%d/%H")
    subdir.mkdir(parents=True, exist_ok=True)
    filename = f"{ts.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
    path = subdir / filename
    path.write_bytes(frame)
    rel = str(path.relative_to(SNAPSHOT_DIR))
    with Session(engine) as session:
        event = Event(ts=ts, kind=kind, snapshot=rel)
        session.add(event)
        session.commit()
        event_id = event.id
    log.info("Snapshot saved: %s (event_id=%d)", path, event_id)
    uploader.enqueue(path, event_id)
    return event_id


def on_motion(ts: datetime) -> None:
    # called from the pir thread - catch everything so one bad event
    # (db hiccup, disk full etc) doesn't kill motion detection for good
    try:
        _handle_motion(ts)
    except Exception:
        log.exception("Error while handling motion event")


def _handle_motion(ts: datetime) -> None:
    mode = state.get("mode")

    if mode == "Manual":
        # in manual mode just log the event — no snapshot, no alarm
        with Session(engine) as session:
            session.add(Event(ts=ts, kind="motion"))
            session.commit()
        log.info("Motion logged (Manual mode — no snapshot)")
        return

    # Stealth and Alert: always save snapshot and upload
    _save_snapshot(ts)

    # Alert: trigger alarm only during configured armed hours
    if mode == "Alert" and _in_armed_hours():
        leds.set_red(True)
        buzzer.beep(1.0)
        # turn red led off after 5 seconds
        threading.Timer(5.0, lambda: leds.set_red(False)).start()


# start all background threads — gunicorn runs with --workers=1 so this
# only executes once; multiple workers would each try to open GPIO and camera
camera_thread = CameraThread(stop_event)
pir_thread = PIRThread(state, stop_event, on_motion)
dht_thread = DHTThread(state, stop_event)
uploader = UploaderThread(state, stop_event, engine)
uploader_thread = threading.Thread(target=uploader.run, daemon=True, name="uploader")


def _requeue_pending_uploads() -> None:
    # the upload queue lives in memory, so after a restart any snapshots that
    # never made it to S3 would be forgotten. put them back in the queue.
    with Session(engine) as session:
        pending = session.scalars(
            select(Event).where(
                Event.snapshot.is_not(None),
                Event.s3_uploaded.is_not(True),
            )
        ).all()
    count = 0
    for e in pending:
        path = SNAPSHOT_DIR / e.snapshot
        if path.exists():
            uploader.enqueue(path, e.id)
            count += 1
    if count:
        log.info("Re-queued %d pending upload(s) from before restart", count)


_requeue_pending_uploads()

camera_thread.start()
pir_thread.start()
dht_thread.start()
uploader_thread.start()

log.info("All threads started (stub=%s)", STUB)


@app.route("/")
def index():
    return render_template("index.html")


def _mjpeg_generator():
    
    # yield jpeg frames in multipart format — browser displays as a live video stream
    while not stop_event.is_set():
        frame = camera_thread.get_frame()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(0.2)


@app.route("/stream")
def stream():
    return Response(
        _mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/state")
def api_state():
    data = state.snapshot()
    data.update(leds.status())  # add led_red and led_green
    return jsonify(data)


@app.route("/api/events")
def api_events():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 200))
    with Session(engine) as session:
        rows = session.scalars(
            select(Event).order_by(desc(Event.ts)).limit(limit)
        ).all()
    return jsonify([
        {
            "id": e.id,
            "ts": e.ts.isoformat(),
            "kind": e.kind,
            "snapshot": e.snapshot,
            "s3_uploaded": e.s3_uploaded,
        }
        for e in rows
    ])


@app.route("/api/mode", methods=["POST"])
def set_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "")
    if mode not in ("Stealth", "Alert", "Manual"):
        return jsonify({"error": "invalid mode"}), 400
    with Session(engine) as session:
        cfg = session.get(Config, "current_mode")
        cfg.value = mode
        session.commit()
    state.update(mode=mode)
    _apply_mode_leds(mode)
    log.info("Mode changed to %s", mode)
    return jsonify({"mode": mode})


@app.route("/api/schedule", methods=["POST"])
def set_schedule():
    data = request.get_json(silent=True) or {}
    start = str(data.get("start", ""))
    end = str(data.get("end", ""))
    # validate HH:MM format - a bad value like 99:99 would otherwise break
    # the armed hours check later
    if not _HHMM_RE.match(start) or not _HHMM_RE.match(end):
        return jsonify({"error": "use HH:MM format (00:00 - 23:59)"}), 400
    with Session(engine) as session:
        session.get(Config, "schedule_start").value = start
        session.get(Config, "schedule_end").value = end
        session.commit()
    state.update(schedule_start=start, schedule_end=end)
    log.info("Armed hours set to %s–%s", start, end)
    return jsonify({"start": start, "end": end})


@app.route("/api/led", methods=["POST"])
def set_led():
    if state.get("mode") != "Manual":
        return jsonify({"error": "LED control only available in Manual mode"}), 403
    data = request.get_json(silent=True) or {}
    color = data.get("color")
    on = bool(data.get("on"))
    if color == "red":
        leds.set_red(on)
    elif color == "green":
        leds.set_green(on)
    else:
        return jsonify({"error": "color must be red or green"}), 400
    return jsonify(leds.status())


@app.route("/api/snapshot", methods=["POST"])
def trigger_snapshot():
    ts = datetime.now(timezone.utc)
    event_id = _save_snapshot(ts, kind="manual")
    if event_id is None:
        return jsonify({"error": "no camera frame yet"}), 503
    return jsonify({"status": "ok", "event_id": event_id})
