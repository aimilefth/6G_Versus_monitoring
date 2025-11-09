# cpu-pyjoules

A concrete monitoring client that:
- inherits the generic push/batching logic from **`aimilefth/base-monitoring-client`**,
- and replaces `monitor_impl.py` with a real **pyJoules** collector.

So this is the image your `docker-compose.yml` runs as `cpu-pyjoules`.

---

## What it does

1. Every `SCRAPE_INTERVAL_S` seconds, it calls pyJoules to read host RAPL counters.
2. It produces a **pyJoules-like dictionary**:

   ```json
   {
     "timestamp": "2025-11-09T08:47:30.123456",
     "duration": 0.1,
     "package-0": 123456,
     "core": 3456
   }
	```

3. That dictionary is converted **in `process_data(...)` of this client** into Prometheus remote-write time series:

   * metric: `pyjoules_remote_write_energy_uj`
   * labels: `component=package-0`, `source=cpu-pyjoules`
   * value: the µJ value
   * timestamp: from pyJoules

4. Every `PUSH_INTERVAL_S` seconds, a batch is sent to Prometheus.

---

## Dockerfile (conceptually)

```dockerfile
FROM aimilefth/base-monitoring-client:latest
RUN pip install --no-cache-dir pyjoules==0.5.1
COPY monitor_impl.py /app/monitor_impl.py
```

So the only “extra” over the base image is: **install pyJoules** and **drop in the real monitor_impl**.

---

## Environment variables (as used in compose)

From the root `.env`:

```ini
REMOTE_WRITE_URL=http://prometheus:9090/api/v1/write
SCRAPE_INTERVAL_S=0.1
PUSH_INTERVAL_S=4
MAX_RETRY_BATCHES=5
SERVICE_LABEL=cpu-pyjoules
LOG_LEVEL=INFO
```

Meaning:

* **`REMOTE_WRITE_URL`** — where to push (inside Docker network, so we use the service name `prometheus`)
* **`SCRAPE_INTERVAL_S`** — pyJoules measurement period
* **`PUSH_INTERVAL_S`** — how often to send a remote-write batch
* **`MAX_RETRY_BATCHES`** — survive short Prometheus outages
* **`SERVICE_LABEL`** — ends up as `source=cpu-pyjoules` in your time series

---

## Volumes & security

The container must be able to **read** the RAPL sysfs paths from the host:

```yaml
volumes:
  - /sys/class/powercap:/sys/class/powercap:ro
  - /sys/devices/virtual/powercap:/sys/devices/virtual/powercap:ro
security_opt:
  - apparmor=docker-pyjoules
  - systempaths=unconfined
```

Alternatively, set `PRIVILEGED=True` in `.env` and use the helper script — then `docker-compose.privileged.yml` will be merged and the service will run privileged.

---

## Building

```bash
cd cpu-pyjoules
./docker_build.sh
```

This builds and pushes `aimilefth/cpu-pyjoules`.

---

## Running (via main compose)

The root `docker-compose.yml` already defines:

```yaml
cpu-pyjoules:
  image: aimilefth/cpu-pyjoules
  ...
```

So from the repo root:

```bash
./docker-compose_helper.sh up -d
```

You should then see in Prometheus time series such as:

* `pyjoules_remote_write_energy_uj{component="package-0",source="cpu-pyjoules"}`
* `pyjoules_remote_write_energy_uj{component="core",source="cpu-pyjoules"}`
* `pyjoules_remote_write_energy_uj{component="uncore",source="cpu-pyjoules"}` (depending on the machine)

---