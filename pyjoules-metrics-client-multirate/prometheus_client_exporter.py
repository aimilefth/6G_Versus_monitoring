# pyjoules-metrics-client-multirate/prometheus_client_exporter.py
import os
import time
import threading
from collections import deque
from datetime import datetime, timezone

from prometheus_client import start_http_server, core
from power_scraper import power_scraper

# ─────────── Configuration via env or defaults ────────────
SCRAPING_FREQ = float(os.getenv("SCRAPING_FREQ", "0.1"))   # internal sampler period (seconds)
HTTP_PORT     = int(os.getenv("HTTP_PORT", "9092"))        # where we expose /metrics
MAX_QUEUE_LEN = int(os.getenv("MAX_QUEUE_LEN", "1000"))    # safety cap (~100 s of samples)

# ──────────── Custom collector that flushes the buffer ────────────
class PowerCollector:
    """
    Converts buffered pyJoules samples into Prometheus samples,
    keeping each sample’s original timestamp so a 1 s Prometheus
    scrape can import the intervening 0 .1 s points.
    """
    def __init__(self, buffer: deque):
        self.buffer = buffer                     # shared ring buffer

    def collect(self):                           # called once per scrape
        while self.buffer:
            sample = self.buffer.popleft()       # oldest first
            ts = sample["ts_seconds"]       # Use the timestamp in seconds

            for comp, uj in sample["energy"].items():
                m = core.Metric(
                    "pyjoules_energy_uj",
                    "Energy consumption (µJ) per component",
                    "gauge",
                )
                m.add_sample(
                    "pyjoules_energy_uj",
                    labels={"component": comp},
                    value=float(uj),
                    timestamp=ts,
                )
                yield m

            dur = core.Metric(
                "pyjoules_measurement_duration_seconds",
                "pyJoules measurement duration of each probe",
                "gauge",
            )
            dur.add_sample(
                "pyjoules_measurement_duration_seconds",
                labels={},
                value=sample["duration"],
                timestamp=ts,
            )
            yield dur


# ──────────── Background sampling thread ──────────────────────────
def sampler(buffer: deque, period: float):
    scraper = power_scraper()
    while True:
        raw = scraper.get_power(interval=period)
        ts_seconds = (
            datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        buffer.append(
            {
                "ts_seconds": ts_seconds,
                "duration": raw["duration"],
                "energy": {k: v for k, v in raw.items() if k not in ("timestamp", "tag", "duration")},
            }
        )
        # keep RAM bounded
        if len(buffer) > MAX_QUEUE_LEN:
            buffer.popleft()


# ──────────── Main ------------------------------------------------
def main() -> None:
    ring_buffer: deque = deque()                 # thread-safe enough for this use
    core.REGISTRY.register(PowerCollector(ring_buffer))
    start_http_server(HTTP_PORT)

    threading.Thread(target=sampler, args=(ring_buffer, SCRAPING_FREQ), daemon=True).start()

    # keep PID 1 alive
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()