import lgpio
import logging
import os
import threading

log = logging.getLogger(__name__)

_RED_PIN = 27
_GREEN_PIN = 22


class LEDController:
    
    # controls both leds via lgpio directly, same reason as pir.py

    def __init__(self):
        self._lock = threading.Lock()
        chip = int(os.environ.get("LGPIO_CHIP", "0"))
        self._h = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self._h, _RED_PIN)
        lgpio.gpio_claim_output(self._h, _GREEN_PIN)
        self._red = False
        self._green = False
        log.info("LED controller ready (red=GPIO%d, green=GPIO%d)", _RED_PIN, _GREEN_PIN)

    def set_red(self, on: bool) -> None:
        with self._lock:
            lgpio.gpio_write(self._h, _RED_PIN, 1 if on else 0)
            self._red = on

    def set_green(self, on: bool) -> None:
        with self._lock:
            lgpio.gpio_write(self._h, _GREEN_PIN, 1 if on else 0)
            self._green = on

    def status(self) -> dict:
        with self._lock:
            return {"led_red": self._red, "led_green": self._green}
