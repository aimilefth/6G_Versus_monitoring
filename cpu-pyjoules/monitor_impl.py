import time
import datetime
import logging
import queue

from pyJoules.energy_meter import measure_energy
from pyJoules.handler import EnergyHandler

log = logging.getLogger("cpu-pyjoules")


class NoSampleProcessedError(Exception):
    pass


class DictHandler(EnergyHandler):
    def __init__(self):
        super().__init__()

    def get_single_dictionary(self) -> dict:
        if not self.traces:
            raise NoSampleProcessedError("No samples have been processed.")

        flattened = self._flaten_trace()
        samples = list(flattened)
        if len(samples) != 1:
            raise ValueError(f"Expected exactly one sample, got {len(samples)}")

        sample = samples[0]
        result = {
            "timestamp": sample.timestamp,
            "tag": sample.tag,
            "duration": sample.duration,
        }
        result.update(sample.energy)
        return result

    def reset(self):
        self.traces = []


class power_scraper:
    def __init__(self):
        self.handler = DictHandler()

    def get_power(self, interval: float = 0.1):
        @measure_energy(handler=self.handler)
        def _sleep(interval: float = 0.1):
            time.sleep(interval)

        _sleep(interval)
        data = self.handler.get_single_dictionary()
        self.handler.reset()
        # normalize timestamp to ISO UTC
        data["timestamp"] = datetime.datetime.utcnow().isoformat()
        return data


# ─────────────────────────────
# API expected by base image
# ─────────────────────────────
def get_power(output_queue: queue.Queue, scrape_interval_s: float, stop_event):
    """
    Scrape pyJoules every scrape_interval_s and push raw dictionaries
    to the first queue.
    """
    scraper = power_scraper()
    log.info("cpu-pyjoules get_power thread started (interval=%s)", scrape_interval_s)
    while not stop_event.is_set():
        data = scraper.get_power(interval=scrape_interval_s)
        try:
            output_queue.put(data, timeout=1)
        except queue.Full:
            log.warning("get_power: raw queue full; dropping measurement")
        # scraper.get_power already slept for interval, so no extra sleep


def process_data(input_queue: queue.Queue, output_queue: queue.Queue, stop_event):
    """
    For now: pass-through, as you requested.
    """
    log.info("cpu-pyjoules process_data thread started (pass-through)")
    while not stop_event.is_set():
        try:
            item = input_queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            output_queue.put(item, timeout=1)
        except queue.Full:
            log.warning("process_data: processed queue full; dropping item")
