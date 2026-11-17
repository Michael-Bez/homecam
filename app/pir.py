import lgpio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable

log = logging.getLogger(__name__)

_GPIO_PIN = 17
_DEBOUNCE_SECS = 2.0  # ignore re-triggers within this window
_POLL_HZ = 0.05       # 20 Hz


class PIRThread(threading.Thread):
    """Polls GPIO17 via lgpio directly.

    gpiozero's lgpio pin factory has a Docker/Pi 5 compatibility issue.
    lgpio direct access works — confirmed by container diagnostic.
    """

    def __init__(self, state, stop_event: threading.Event,
                 on_motion: Callable[[datetime], None]) -> None:
        super().__init__(daemon=True, name="pir")
        self._state = state
        self._stop = stop_event
        self._on_motion = on_motion

    def run(self) -> None:
        chip = int(os.environ.get("LGPIO_CHIP", "0"))
        h = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_input(h, _GPIO_PIN, lgpio.SET_PULL_DOWN)
        log.info("PIR thread started on GPIO%d (lgpio chip=%d)", _GPIO_PIN, chip)

        last_state = 0
        last_trigger = 0.0
        try:
            while not self._stop.is_set():
                state = lgpio.gpio_read(h, _GPIO_PIN)
                now = time.monotonic()

                if state == 1 and last_state == 0:        # rising edge
                    if now - last_trigger >= _DEBOUNCE_SECS:
                        ts = datetime.now(timezone.utc)
                        count = self._state.increment("motion_count")
                        self._state.update(last_motion=ts.isoformat())
                        log.info("Motion detected (event #%d) at %s", count, ts.isoformat())
                        self._on_motion(ts)
                        last_trigger = now

                last_state = state
                time.sleep(_POLL_HZ)
        finally:
            lgpio.gpiochip_close(h)
            log.info("PIR thread stopped")

