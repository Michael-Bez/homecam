import threading


class ThreadSafeState:
    # shared data read by flask routes and written by sensor threads
    # lock stops two threads reading/writing at the same time

    def __init__(self, **initial) -> None:
        self._lock = threading.Lock()
        self._data: dict = {
            "last_motion": None,
            "motion_count": 0,
            "uploader_status": "idle",
            "upload_queue_depth": 0,
            "mode": "Stealth",
            "temperature": None,
            "humidity": None,
            "schedule_start": "22:00",
            "schedule_end": "06:00",
        }
        # override defaults with values loaded from DB at startup
        self._data.update(initial)

    def get(self, key: str):
        with self._lock:
            return self._data[key]

    def update(self, **kwargs) -> None:
        with self._lock:
            self._data.update(kwargs)

    def increment(self, key: str) -> int:
        with self._lock:
            self._data[key] += 1
            return self._data[key]

    def snapshot(self) -> dict:
        # return a copy so the caller can safely serialise without holding the lock
        with self._lock:
            return dict(self._data)
