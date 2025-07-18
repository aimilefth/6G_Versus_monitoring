import os, time, threading, queue, snappy, requests
from collections import defaultdict
from datetime import datetime, timezone

from remote_pb2 import WriteRequest, TimeSeries, Label, Sample
from power_scraper import power_scraper

# --- Configuration ---
URL         = os.getenv("REMOTE_WRITE_URL", "http://localhost:9090/api/v1/write")
STEP        = float(os.getenv("SAMPLING_PERIOD_S", "0.1"))  # 100 ms
BATCH_SIZE  = int(os.getenv("BATCH_SIZE", "100"))            # 1 second worth of data per batch

# --- Globals ---
scraper = power_scraper()
q = queue.Queue(maxsize=1000)  # Bounded queue to protect RAM

# ---------- Sampler Thread (collects data) --------------------------------
def sampler():
    """
    Continuously samples power data at the STEP interval and puts it into a queue.
    """
    print(f"Starting sampler with a {STEP}s interval.")
    while True:
        # Get raw data from your scraper
        raw_data = scraper.get_power(interval=STEP)

        # Convert timestamp to milliseconds since epoch (as required by remote-write spec)
        ts_ms = int(
            datetime.fromisoformat(raw_data["timestamp"].replace("Z", "+00:00"))
            .replace(tzinfo=timezone.utc).timestamp() * 1000
        )

        # Clean up the data, keeping only the energy components
        raw_data.pop("duration")
        raw_data.pop("timestamp")
        raw_data.pop("tag", None)

        # Put the processed data into the queue for the shipper
        q.put((ts_ms, raw_data))  # This will block if the queue is full

threading.Thread(target=sampler, daemon=True).start()

# ---------- Shipper Thread (batches and sends data) ----------------------
def shipper():
    """
    Collects data from the queue, batches it, and sends it to Prometheus
    via the remote-write endpoint.
    """
    session = requests.Session()
    headers = {
        "Content-Encoding": "snappy",
        "Content-Type": "application/x-protobuf",
        "X-Prometheus-Remote-Write-Version": "0.1.0",
    }
    print(f"Starting shipper. Will push batches of {BATCH_SIZE} samples.")

    while True:
        # 1. Collect a batch of data from the queue
        batch = []
        for _ in range(BATCH_SIZE):
            batch.append(q.get()) # This blocks until an item is available

        # 2. Group samples by their time series identifier (the labels)
        #    A defaultdict is used for convenience.
        #    The key will be a tuple of label pairs, e.g., (('__name__', 'pyjoules_energy_uj'), ('component', 'core_0'))
        series_map = defaultdict(list)

        for ts_ms, energy_data in batch:
            for component, uj_value in energy_data.items():
                # The unique identifier for a time series is its set of labels.
                series_key = (
                    ("__name__", "pyjoules_energy_uj"),
                    ("component", str(component)),
                )
                # Append the new sample to the list for this series
                sample = Sample(value=float(uj_value), timestamp=ts_ms)
                series_map[series_key].append(sample)

        # 3. Build the Protobuf WriteRequest from the grouped data
        req = WriteRequest()
        for series_key_tuple, samples in series_map.items():
            ts = req.timeseries.add()
            # Add labels from our key
            for name, value in series_key_tuple:
                ts.labels.add(name=name, value=value)
            # Add all the collected samples for this series
            ts.samples.extend(samples)

        # 4. Serialize, compress, and send the request
        if not req.timeseries:
            continue # Don't send empty requests

        payload = snappy.compress(req.SerializeToString())
        try:
            r = session.post(URL, data=payload, headers=headers, timeout=5)
            r.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
            total_samples = sum(len(ts.samples) for ts in req.timeseries)
            print(f"Pushed {len(req.timeseries)} time series with a total of {total_samples} samples. Status: {r.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error pushing metrics: {e}")


threading.Thread(target=shipper, daemon=True).start()

# ---------- Keep the main process (PID 1 in Docker) alive ----------------
print("Sampler and Shipper threads started. Monitoring power consumption...")
while True:
    time.sleep(3600)