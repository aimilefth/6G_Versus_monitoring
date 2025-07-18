import os, time, threading, queue, snappy, requests
from datetime import datetime, timezone

from remote_pb2 import WriteRequest, TimeSeries, Label, Sample
from power_scraper import power_scraper                           # your file

URL         = os.getenv("REMOTE_WRITE_URL", "http://localhost:9090/api/v1/write")
STEP        = float(os.getenv("SAMPLING_PERIOD_S", "0.1"))         # 100 ms
BATCH_SIZE  = int(os.getenv("BATCH_SIZE", "10"))                   # 1 s batch

scraper  = power_scraper()
q        = queue.Queue(maxsize=1000)     # protect RAM

# ---------- sampler thread -------------------------------------------------
def sampler():
    while True:
        raw = scraper.get_power(interval=STEP)
        ts_ms = int(
            datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
            .replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        raw.pop("duration"); raw.pop("timestamp"); raw.pop("tag", None)
        q.put((ts_ms, raw))              # blocks if queue full

threading.Thread(target=sampler, daemon=True).start()

# ---------- shipper thread -------------------------------------------------
def shipper():
    session = requests.Session()
    headers = {
        "Content-Encoding": "snappy",
        "Content-Type": "application/x-protobuf",
        "X-Prometheus-Remote-Write-Version": "0.1.0",
    }

    while True:
        batch = []
        for _ in range(BATCH_SIZE):          # collect 1 second worth
            batch.append(q.get())

        req = WriteRequest()
        for ts_ms, energy in batch:
            for comp, uj in energy.items():
                series = req.timeseries.add()
                series.labels.extend([
                    Label(name="__name__", value="pyjoules_energy_uj"),
                    Label(name="component", value=str(comp)),
                ])
                series.samples.append(Sample(value=float(uj), timestamp=ts_ms))

        payload = snappy.compress(req.SerializeToString())
        r = session.post(URL, data=payload, headers=headers, timeout=5)
        r.raise_for_status()                # raises if 4xx/5xx
        print(f"Pushed {len(req.timeseries)} samples")

threading.Thread(target=shipper, daemon=True).start()

# ---------- keep PID 1 alive ----------------------------------------------
while True:
    time.sleep(3600)
