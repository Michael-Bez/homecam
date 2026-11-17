import lgpio
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_BUZZER_PIN = 18
_FREQ = 1000  # 1kHz tone


class Buzzer:
    def __init__(self):
        chip = int(os.environ.get("LGPIO_CHIP", "0"))
        self._h = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self._h, _BUZZER_PIN)
        log.info("Buzzer ready (GPIO%d)", _BUZZER_PIN)

    def beep(self, duration: float = 1.0) -> None:
        # run in its own thread so it doesn't block thhe pir callback
        threading.Thread(target=self._beep, args=(duration,), daemon=True).start()

    def _beep(self, duration: float) -> None:
        lgpio.tx_pwm(self._h, _BUZZER_PIN, _FREQ, 50)
        time.sleep(duration)
        lgpio.tx_pwm(self._h, _BUZZER_PIN, _FREQ, 0)  # duty=0 stops sound
