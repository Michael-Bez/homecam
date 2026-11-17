import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_GPIO_PIN = 4 

_READ_EVERY = 30    # seconds between readings


class DHTThread(threading.Thread):

    def __init__(self, state, stop_event: threading.Event) -> None:
        super().__init__(daemon=True, name="dht")
        self._state = state
        self._stop = stop_event

    def run(self) -> None:
        # must be set before importing board/adafruit_dht so blinka detects the pi
        os.environ.setdefault("BLINKA_RASPBERRY_PI", "1")
        try:
            import adafruit_dht
            import board
            sensor = adafruit_dht.DHT22(board.D4, use_pulseio=False)
        except Exception as e:
            log.error("DHT22 init failed — temp/humidity will show as unavailable: %s", e)
            return

        log.info("DHT22 thread started on GPIO%d", _GPIO_PIN)
        while not self._stop.is_set():
            try:
                temp = sensor.temperature
                hum = sensor.humidity
                if temp is not None and hum is not None:
                    self._state.update(temperature=round(temp, 1), humidity=round(hum, 1))
            except RuntimeError as e:
                # dht22 misreads are common, just skip and retry next cycle
                log.debug("DHT22 read error (retrying): %s", e)
            except Exception as e:
                log.warning("DHT22 unexpected error: %s", e)

            # wait _READ_EVERY seconds but check stop_event every 100ms
            for _ in range(_READ_EVERY * 10):
                if self._stop.is_set():
                    return
                time.sleep(0.1)
