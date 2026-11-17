import io
import logging
import threading
import time

log = logging.getLogger(__name__)


class CameraThread(threading.Thread):

    """
    Continuously captures JPEG frames from the CSI camera at ~5 fps.

    get_frame() returns the latest bytes from any thread without blocking long.
    The frame is reused for both the MJPEG stream and motion snapshots.

    """

    def __init__(self, stop_event: threading.Event) -> None:
        super().__init__(daemon=True, name="camera")
        self._stop = stop_event
        self._frame: bytes | None = None
        self._lock = threading.Lock()

    def run(self) -> None:
        # Import is deferred so the module loads on dev PC without picamera2 installed.
        from picamera2 import Picamera2

        cam = Picamera2()
        cfg = cam.create_video_configuration(main={"size": (640, 480)})
        cam.configure(cfg)
        cam.start()
        log.info("Camera started (640x480 @ 5 fps)")

        try:
            while not self._stop.is_set():
                buf = io.BytesIO()
                cam.capture_file(buf, format="jpeg")
                with self._lock:
                    self._frame = buf.getvalue()
                time.sleep(0.2)  # 5 fps — light on CPU, plenty for surveillance
        finally:
            cam.stop()
            log.info("Camera stopped")

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame
