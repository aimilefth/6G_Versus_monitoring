# base-monitoring-client

A **generic Prometheus remote-write client**.

You run this in a container, and it:

1. spins up two worker threads from a module called `monitor_impl`,
2. collects whatever those threads produce,
3. **expects** `process_data(...)` to output **already normalized** Prometheus remote-write records,
4. batches and **pushes** it to Prometheus every `PUSH_INTERVAL_S` seconds,
5. retries failed batches.

Your concrete monitoring client (like `cpu-pyjoules`) only needs to supply **one file**: `monitor_impl.py`.

---

## Pipeline

The main script is `remote_write_pusher.py`. On startup it:

1. creates two queues:
   - **raw** queue (what your collector writes into)
   - **processed** queue (what your optional processor writes into)
2. starts:
   - `monitor_impl.get_power(raw_queue, SCRAPE_INTERVAL_S, stop_event)`
   - `monitor_impl.process_data(raw_queue, proc_queue, stop_event)`
3. every `PUSH_INTERVAL_S` seconds:
   - drain `proc_queue`
   - build a protobuf `WriteRequest`
   - compress with snappy
   - POST to Prometheus

If the POST fails, the batch is kept in memory (FIFO) up to `MAX_RETRY_BATCHES`.

---

## Expected `monitor_impl.py`

You must provide two functions (the base repo ships with a **dummy** version):

```python
def get_power(output_queue, scrape_interval_s, stop_event):
    # collect measurements at scrape_interval_s
    # and put dictionaries in output_queue
    ...

def process_data(input_queue, output_queue, stop_event):
    # optional: clean / aggregate / enrich
    # and put final records in output_queue
    ...
```

The **cpu-pyjoules** client overwrites this with a real pyJoules collector.

---

## Accepted record formats

   ```json
   {
     "metric": "my_metric",
     "labels": {"source": "foo"},
     "value": 123.4,
     "timestamp_ms": 1731080000000
   }
   ```

   → sent 1:1

---

## Environment variables

All of these can be set from Compose or `.env`:

* `REMOTE_WRITE_URL` (default: `http://prometheus:9090/api/v1/write`)
* `SCRAPE_INTERVAL_S` — how often your collector should read the host
* `PUSH_INTERVAL_S` — how often we send a remote-write batch
* `MAX_RETRY_BATCHES` — max batches kept in memory when Prometheus is down
* `RAW_QUEUE_SIZE`, `PROC_QUEUE_SIZE` — backpressure
* `LOG_LEVEL` — `INFO` / `DEBUG` / ...
* `SERVICE_LABEL` — added to records coming from pyJoules-like dictionaries
* `METRIC_DEFAULT` — default metric name (`pyjoules_remote_write_energy_uj`)

---

## Building

```bash
cd base-monitoring-client
./docker_build.sh
```

This produces/pushes `aimilefth/base-monitoring-client`.

You then `FROM` that image in your concrete client (see `cpu-pyjoules/Dockerfile`).

---

## Why this exists

In the old repo, each exporter reimplemented:

* threading
* batching
* remote-write pusher
* error handling

Now that logic lives in **one** place. Every new sensor/telemetry client just plugs in via `monitor_impl.py`.