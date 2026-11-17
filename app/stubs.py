# fake sensor implementations for dev pc testing (STUB_SENSORS=1)
# drop-in replacements for all hardware classes

import io
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)


class CameraThread(threading.Thread):
    def __init__(self, stop_event: threading.Event) -> None:
        super().__init__(daemon=True, name="camera-stub")
        self._stop = stop_event
        self._frame: bytes | None = None
        self._lock = threading.Lock()

    def run(self) -> None:
        log.info("[STUB] Camera thread started")
        while not self._stop.is_set():
            img = Image.new("RGB", (640, 480), color=(20, 20, 40))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "STUB CAMERA", fill=(0, 255, 0))
            draw.text((10, 30), datetime.now().strftime("%H:%M:%S"), fill=(200, 200, 200))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            with self._lock:
                self._frame = buf.getvalue()
            time.sleep(0.2)
        log.info("[STUB] Camera thread stopped")

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame


class PIRThread(threading.Thread):
    def __init__(
        self,
        state,
        stop_event: threading.Event,
        on_motion: Callable[[datetime], None],
    ) -> None:
        super().__init__(daemon=True, name="pir-stub")
        self._state = state
        self._stop = stop_event
        self._on_motion = on_motion

    def run(self) -> None:
        log.info("[STUB] PIR thread started — fires every 15s")
        while not self._stop.is_set():
            for _ in range(150):
                if self._stop.is_set():
                    return
                time.sleep(0.1)
            ts = datetime.now(timezone.utc)
            count = self._state.increment("motion_count")
            self._state.update(last_motion=ts.isoformat())
            log.info("[STUB] Motion event #%d", count)
            self._on_motion(ts)


class LEDController:
    def __init__(self):
        self._red = False
        self._green = False
        log.info("[STUB] LED controller ready")

    def set_red(self, on: bool) -> None:
        self._red = on
        log.info("[STUB] Red LED: %s", "ON" if on else "OFF")

    def set_green(self, on: bool) -> None:
        self._green = on
        log.info("[STUB] Green LED: %s", "ON" if on else "OFF")

    def status(self) -> dict:
        return {"led_red": self._red, "led_green": self._green}


class Buzzer:
    def beep(self, duration: float = 1.0) -> None:
        log.info("[STUB] Buzzer: beep for %.1fs", duration)


class DHTThread(threading.Thread):
    def __init__(self, state, stop_event: threading.Event) -> None:
        super().__init__(daemon=True, name="dht-stub")
        self._state = state
        self._stop = stop_event

    def run(self) -> None:
        log.info("[STUB] DHT22 thread started — returning fake values")
        while not self._stop.is_set():
            self._state.update(temperature=22.5, humidity=55.0)
            for _ in range(300):
                if self._stop.is_set():
                    return
                time.sleep(0.1)
