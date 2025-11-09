# base-monitoring-client/remote_write_pusher.py
import os
import time
import threading
import logging
import queue
from collections import deque, defaultdict
from datetime import datetime, timezone

import requests
import snappy

from remote_pb2 import WriteRequest, Sample
import monitor_impl  # will be provided/overridden by derived image

# ────────────────────── config ──────────────────────
REMOTE_WRITE_URL   = os.getenv("REMOTE_WRITE_URL", "http://prometheus:9090/api/v1/write")
SCRAPE_INTERVAL_S  = float(os.getenv("SCRAPE_INTERVAL_S", "0.1"))
PUSH_INTERVAL_S    = float(os.getenv("PUSH_INTERVAL_S", "4"))
MAX_RETRY_BATCHES  = int(os.getenv("MAX_RETRY_BATCHES", "5"))
RAW_QUEUE_SIZE     = int(os.getenv("RAW_QUEUE_SIZE", "1000"))
PROC_QUEUE_SIZE    = int(os.getenv("PROC_QUEUE_SIZE", "1000"))
LOG_LEVEL          = os.getenv("LOG_LEVEL", "INFO").upper()
SERVICE_LABEL      = os.getenv("SERVICE_LABEL", "monitor")
METRIC_DEFAULT     = os.getenv("METRIC_DEFAULT", "pyjoules_remote_write_energy_uj")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("base-monitoring-client")


def _iso_to_ms(iso_str: str) -> int:
    # tolerate plain UTC isoformat without Z
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def normalize_record(record: dict):
    """
    We support two shapes:
    1) NORMALIZED:
       {
         "metric": "...",
         "labels": {...},
         "value": float,
         "timestamp_ms": int
       }
       -> yields exactly one normalized record

    2) pyJoules-like (what your current clients produce):
       {
         "timestamp": "...iso...",
         "duration": float,
         "tag": "...",           # optional
         "<component>": numeric, # e.g. package-0, core, dram, ...
         ...
       }
       -> yields one normalized record per component
    """
    # case 1: already normalized
    if (
        isinstance(record, dict)
        and "metric" in record
        and "labels" in record
        and "value" in record
        and "timestamp_ms" in record
    ):
        return [record]

    # case 2: pyjoules-ish
    if isinstance(record, dict) and "timestamp" in record:
        ts_ms = _iso_to_ms(record["timestamp"])
        duration = record.pop("duration", None)
        record.pop("tag", None)
        record.pop("timestamp", None)

        norm = []
        for component, uj_val in record.items():
            try:
                v = float(uj_val)
            except (ValueError, TypeError):
                continue
            norm.append(
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
        # 'duration' is not emitted as separate metric here; the concrete
        # monitor could do it in its own process_data step if needed
        return norm

    log.warning("normalize_record: unsupported record shape; dropping: %r", record)
    return []


def build_write_request(records):
    """
    records: iterable of normalized records
    normalized record:
       {metric, labels: dict, value: float, timestamp_ms: int}
    """
    series_map = defaultdict(list)  # key -> list[Sample]

    for rec in records:
        metric = rec["metric"]
        labels = rec.get("labels", {})
        ts_ms = int(rec["timestamp_ms"])
        value = float(rec["value"])

        # build sorted label tuple to have deterministic TS keys
        label_items = [("__name__", metric)] + sorted(labels.items())
        key = tuple(label_items)
        series_map[key].append(Sample(value=value, timestamp=ts_ms))

    req = WriteRequest()
    for key, samples in series_map.items():
        ts = req.timeseries.add()
        for name, value in key:
            lab = ts.labels.add()
            lab.name = name
            lab.value = value
        ts.samples.extend(samples)

    return req


def push_write_request(session: requests.Session, req: WriteRequest):
    payload = snappy.compress(req.SerializeToString())
    headers = {
        "Content-Encoding": "snappy",
        "Content-Type": "application/x-protobuf",
        "X-Prometheus-Remote-Write-Version": "0.1.0",
    }
    resp = session.post(REMOTE_WRITE_URL, data=payload, headers=headers, timeout=5)
    resp.raise_for_status()
    return resp


def start_pipeline():
    raw_queue = queue.Queue(maxsize=RAW_QUEUE_SIZE)
    proc_queue = queue.Queue(maxsize=PROC_QUEUE_SIZE)
    stop_event = threading.Event()

    # start get_power thread
    threading.Thread(
        target=monitor_impl.get_power,
        args=(raw_queue, SCRAPE_INTERVAL_S, stop_event),
        daemon=True,
        name="get_power_thread",
    ).start()

    # start process_data thread
    threading.Thread(
        target=monitor_impl.process_data,
        args=(raw_queue, proc_queue, stop_event),
        daemon=True,
        name="process_data_thread",
    ).start()

    log.info("Started get_power and process_data threads")
    return proc_queue, stop_event


def main():
    proc_queue, stop_event = start_pipeline()

    retry_batches = deque()  # each item is list[normalized_records]
    session = requests.Session()

    log.info("Remote write loop started: push every %ss", PUSH_INTERVAL_S)

    try:
        while True:
            deadline = time.time() + PUSH_INTERVAL_S
            current_raw = []

            # collect items until deadline
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    item = proc_queue.get(timeout=remaining)
                    current_raw.append(item)
                except queue.Empty:
                    # no data right now, loop until deadline
                    continue

            # normalize what we just collected
            current_norm = []
            for r in current_raw:
                current_norm.extend(normalize_record(r))

            # build list of batches to try (old retries first, then current)
            batches_to_try = []
            while retry_batches:
                batches_to_try.append(retry_batches.popleft())
            if current_norm:
                batches_to_try.append(current_norm)

            # nothing to send? loop again
            if not batches_to_try:
                continue

            for batch in batches_to_try:
                if not batch:
                    continue
                req = build_write_request(batch)
                try:
                    resp = push_write_request(session, req)
                    log.info(
                        "Pushed batch with %d normalized samples (HTTP %s)",
                        sum(len(ts.samples) for ts in req.timeseries),
                        resp.status_code,
                    )
                except Exception as e:
                    log.error("Push failed: %s", e)
                    retry_batches.append(batch)
                    # enforce FIFO max
                    while len(retry_batches) > MAX_RETRY_BATCHES:
                        dropped = retry_batches.popleft()
                        dropped_count = sum(
                            1 for _ in dropped
                        )  # approximate/log only
                        log.warning(
                            "Dropping oldest retry batch with ~%d records due to MAX_RETRY_BATCHES",
                            dropped_count,
                        )
    except KeyboardInterrupt:
        log.info("Received shutdown, stopping ...")
        stop_event.set()


if __name__ == "__main__":
    main()
