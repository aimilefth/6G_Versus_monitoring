# cpu-pyjoules/monitor_impl.py
import os
import time
import datetime
import logging
import queue

from pyJoules.energy_meter import measure_energy
from pyJoules.handler import EnergyHandler

log = logging.getLogger("cpu-pyjoules")

METRIC_DEFAULT = os.getenv("METRIC_DEFAULT", "pyjoules_remote_write_energy_uj")
SERVICE_LABEL  = os.getenv("SERVICE_LABEL", "cpu-pyjoules")


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


def _iso_to_ms(iso_str: str) -> int:
    # allow "2025-11-09T08:47:30.123456" kind of strings
    dt = datetime.datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


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


# ─────────────────────────────
# processor (now does normalization)
# ─────────────────────────────
def process_data(input_queue: queue.Queue, output_queue: queue.Queue, stop_event):
    """
    Convert pyJoules-shaped dicts to *normalized* Prometheus records.
    """
    log.info("cpu-pyjoules process_data thread started (normalizing)")
    while not stop_event.is_set():
        try:
            raw = input_queue.get(timeout=1)
        except queue.Empty:
            continue

        if not isinstance(raw, dict) or "timestamp" not in raw:
            log.warning("process_data: unexpected raw record %r", raw)
            continue

        ts_ms = _iso_to_ms(raw["timestamp"])
        raw.pop("tag", None)
        duration = raw.pop("duration", None)
        raw.pop("timestamp", None)

        normalized_batch = []

        for component, uj_val in raw.items():
            try:
                v = float(uj_val)
            except (TypeError, ValueError):
                continue

            normalized_batch.append(
                {
                    "metric": METRIC_DEFAULT,
                    "labels": {
                        "component": str(component),
                        "source": SERVICE_LABEL,
                    },
                    "value": v,
                    "timestamp_ms": ts_ms,
                }
            )

        # you could also emit duration as a separate metric here if you want
        # e.g. pyjoules_remote_write_duration_s
        # if duration is not None:
        #     normalized_batch.append(...)

        if not normalized_batch:
            continue

        try:
            # we push the whole list and let the pusher flatten it
            output_queue.put(normalized_batch, timeout=1)
        except queue.Full:
            log.warning("process_data: processed queue full; dropping batch")
