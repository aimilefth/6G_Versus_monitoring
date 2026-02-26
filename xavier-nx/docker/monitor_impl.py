import os
import time
import glob
import datetime
import logging
import queue

log = logging.getLogger("xavier-nx")

# Metric names (override via env if you want)
METRIC_POWER_W = os.getenv("METRIC_POWER_W", "xavier_nx_power_watts")
METRIC_VOLTAGE_V = os.getenv("METRIC_VOLTAGE_V", "xavier_nx_voltage_volts")
METRIC_CURRENT_A = os.getenv("METRIC_CURRENT_A", "xavier_nx_current_amps")

SERVICE_LABEL = os.getenv("SERVICE_LABEL", "xavier-nx")


import datetime

def get_value_from_read(path):
    try: 
        with open(path, 'r') as device_file:
            return device_file.read()
    except Exception as e:
        print(f"Error in get_value_from_read: {e}")
        return None

class power_scraper:
    # https://docs.nvidia.com/jetson/archives/r35.4.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonXavierNxSeriesAndJetsonAgxXavierSeries.html#jetson-xavier-nx-series
    def __init__(self) -> None:
        self.name = ['VDD_IN', 'VDD_CPU_GPU_CV', 'VDD_SOC']       
        
        self.address = [0, 0, 0]

        self.channel = [1, 2, 3]

        self.description = ['Total Module Power.', 
                            'Total power consumed by CPU, CPU and CV cores i.e. DLA and PVA',
                            'Power consumed by SOC core which supplies to memory subsystem and various engines like nvdec, nvenc, vi, vic, isp etc.',]
        
    def get_power(self):
        power = {}
        for (address, channel, name) in zip(self.address, self.channel, self.name):
            # Values from files are milli
            v = int(get_value_from_read(f'/sys/bus/i2c/drivers/ina3221/7-004{address}/hwmon/hwmon{address+5}/in{channel}_input'))/1000
            i = int(get_value_from_read(f'/sys/bus/i2c/drivers/ina3221/7-004{address}/hwmon/hwmon{address+5}/curr{channel}_input'))/1000
            p = v * i
            temp_dir = {'Voltage': v, 'Current': i, 'Power': p}
            power[name] = temp_dir
        power['timestamp'] = datetime.datetime.utcnow().isoformat()
        return power

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
    """Scrape sysfs every scrape_interval_s and push raw dicts."""
    scraper = power_scraper()
    log.info("xavier-nx get_power thread started (interval=%s)", scrape_interval_s)

    while not stop_event.is_set():
        t0 = time.time()
        data = scraper.get_power()

        try:
            output_queue.put(data, timeout=1)
        except queue.Full:
            log.warning("get_power: raw queue full; dropping measurement")

        # keep a roughly stable interval (scrape itself takes some time)
        elapsed = time.time() - t0
        sleep_s = max(0.0, float(scrape_interval_s) - elapsed)
        if sleep_s:
            time.sleep(sleep_s)


def process_data(input_queue: queue.Queue, output_queue: queue.Queue, stop_event):
    """Convert raw scraper dicts to normalized Prometheus remote-write records."""
    log.info("xavier-nx process_data thread started (normalizing)")

    while not stop_event.is_set():
        try:
            raw = input_queue.get(timeout=1)
        except queue.Empty:
            continue

        if not isinstance(raw, dict) or "timestamp" not in raw:
            log.warning("process_data: unexpected raw record %r", raw)
            continue

        try:
            ts_ms = _iso_to_ms(str(raw["timestamp"]))
        except Exception as e:
            log.warning("process_data: bad timestamp %r (%s)", raw.get("timestamp"), e)
            continue

        normalized_batch: list[dict] = []

        for component, payload in raw.items():
            if component == "timestamp":
                continue

            # regular rails: expect a dict with Voltage/Current/Power
            if not isinstance(payload, dict):
                continue

            v = payload.get("Voltage")
            i = payload.get("Current")
            p = payload.get("Power")

            try:
                if v is not None:
                    normalized_batch.append(
                        {
                            "metric": METRIC_VOLTAGE_V,
                            "labels": {"component": str(component), "source": SERVICE_LABEL},
                            "value": float(v),
                            "timestamp_ms": ts_ms,
                        }
                    )
                if i is not None:
                    normalized_batch.append(
                        {
                            "metric": METRIC_CURRENT_A,
                            "labels": {"component": str(component), "source": SERVICE_LABEL},
                            "value": float(i),
                            "timestamp_ms": ts_ms,
                        }
                    )
                if p is not None:
                    normalized_batch.append(
                        {
                            "metric": METRIC_POWER_W,
                            "labels": {"component": str(component), "source": SERVICE_LABEL},
                            "value": float(p),
                            "timestamp_ms": ts_ms,
                        }
                    )
            except (TypeError, ValueError):
                continue

        if not normalized_batch:
            continue

        try:
            # push the whole list and let the pusher flatten it
            output_queue.put(normalized_batch, timeout=1)
        except queue.Full:
            log.warning("process_data: processed queue full; dropping batch")
