# base-monitoring-client/remote_write_pusher.py
import os
import time
import threading
import logging
import queue
from collections import deque, defaultdict

import requests
import snappy

from remote_pb2 import WriteRequest, Sample
import monitor_impl  # provided/overridden by derived image

REMOTE_WRITE_URL = os.getenv("REMOTE_WRITE_URL", "http://prometheus:9090/api/v1/write")
PUSH_INTERVAL_S = float(os.getenv("PUSH_INTERVAL_S", "4"))
MAX_RETRY_BATCHES = int(os.getenv("MAX_RETRY_BATCHES", "5"))
RAW_QUEUE_SIZE = int(os.getenv("RAW_QUEUE_SIZE", "1000"))
PROC_QUEUE_SIZE = int(os.getenv("PROC_QUEUE_SIZE", "1000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("base-monitoring-client")


def build_write_request(records):
    """
    records: iterable of normalized records:
       {
         "metric": str,
         "labels": dict[str,str],
         "value": float,
         "timestamp_ms": int
       }
    """
    series_map = defaultdict(list)

    for rec in records:
        try:
            metric = rec["metric"]
            labels = rec.get("labels", {})
            ts_ms = int(rec["timestamp_ms"])
            value = float(rec["value"])
        except (KeyError, ValueError, TypeError) as e:
            log.warning(
                "build_write_request: bad normalized record %r (%s) - dropping", rec, e
            )
            continue

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
    """Send the protobuf to Prometheus and log response text on errors."""
    payload = snappy.compress(req.SerializeToString())
    headers = {
        "Content-Encoding": "snappy",
        "Content-Type": "application/x-protobuf",
        "X-Prometheus-Remote-Write-Version": "0.1.0",
    }
    resp = session.post(REMOTE_WRITE_URL, data=payload, headers=headers, timeout=5)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        detail = resp.text.strip()
        if detail:
            log.error("Remote write HTTP %s: %s", resp.status_code, detail[:500])
        else:
            log.error("Remote write HTTP %s with empty response body", resp.status_code)
        raise
    return resp


def start_pipeline(scrape_interval_s: float):
    """Start collector + processor threads and return the queues + stop event + threads."""
    raw_queue = queue.Queue(maxsize=RAW_QUEUE_SIZE)
    proc_queue = queue.Queue(maxsize=PROC_QUEUE_SIZE)
    stop_event = threading.Event()

    collector_thread = threading.Thread(
        target=monitor_impl.get_power,
        args=(raw_queue, scrape_interval_s, stop_event),
        daemon=True,
        name="get_power_thread",
    )
    processor_thread = threading.Thread(
        target=monitor_impl.process_data,
        args=(raw_queue, proc_queue, stop_event),
        daemon=True,
        name="process_data_thread",
    )

    collector_thread.start()
    processor_thread.start()

    log.info("Started get_power and process_data threads")
    # return the threads so the main loop can watch them
    return proc_queue, stop_event, [collector_thread, processor_thread]


def main():
    # collector interval
    scrape_interval_s = float(os.getenv("SCRAPE_INTERVAL_S", "0.1"))
    proc_queue, stop_event, worker_threads = start_pipeline(scrape_interval_s)

    retry_batches = deque()
    session = requests.Session()

    log.info("Remote write loop started: push every %ss", PUSH_INTERVAL_S)

    try:
        # run until we're told to stop (or a worker dies)
        while not stop_event.is_set():
            # ---- worker health guard ----
            for t in worker_threads:
                if not t.is_alive():
                    log.error("Worker thread %s died; stopping pipeline", t.name)
                    stop_event.set()
                    break
            if stop_event.is_set():
                break

            # ---- collect records until next push ----
            deadline = time.time() + PUSH_INTERVAL_S
            current_items = []

            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    item = proc_queue.get(timeout=remaining)
                    current_items.append(item)
                except queue.Empty:
                    continue

            # ---- normalize (flatten) what processor gave us ----
            normalized_records = []
            for item in current_items:
                if isinstance(item, dict):
                    normalized_records.append(item)
                elif isinstance(item, (list, tuple)):
                    for sub in item:
                        if isinstance(sub, dict):
                            normalized_records.append(sub)
                        else:
                            log.warning(
                                "processor emitted non-dict inside list: %r", sub
                            )
                else:
                    log.warning("processor emitted non-dict: %r", item)

            # start with old retry batches
            batches_to_try = []
            while retry_batches:
                batches_to_try.append(retry_batches.popleft())

            # and add the fresh one
            if normalized_records:
                batches_to_try.append(normalized_records)

            if not batches_to_try:
                continue

            # ---- push batches ----
            for batch in batches_to_try:
                if not batch:
                    continue
                req = build_write_request(batch)
                try:
                    resp = push_write_request(session, req)
                    log.info(
                        "Pushed batch with %d time series (HTTP %s)",
                        len(req.timeseries),
                        resp.status_code,
                    )
                except Exception as e:
                    log.error("Push failed: %s", e)
                    retry_batches.append(batch)
                    while len(retry_batches) > MAX_RETRY_BATCHES:
                        _ = retry_batches.popleft()
                        log.warning(
                            "Dropping oldest retry batch due to MAX_RETRY_BATCHES"
                        )

    except KeyboardInterrupt:
        log.info("Shutting down ...")
        stop_event.set()


if __name__ == "__main__":
    main()
