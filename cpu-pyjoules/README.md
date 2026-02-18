# cpu-pyjoules (client stack)

This is the first concrete monitoring client stack and acts as a template for creating more clients.

It:

- runs a container that reads CPU energy from host RAPL counters (via PyJoules),
- converts raw PyJoules output into **normalized** Prometheus remote-write records,
- pushes batches to a Prometheus server reachable via a **host/public address** (not Docker DNS)

---

## What’s in this directory

- `docker-compose.yml`  
  Runs the client container and points it to Prometheus using:
  - `CLIENT_CPU_PROMETHEUS_HOST`
  - `CLIENT_CPU_PROMETHEUS_PORT`

- `docker-compose.privileged.yml`  
  Optional overlay enabling privileged mode (controlled by `PRIVILEGED=True` in `.env`)

- `.env`  
  Client-specific configuration (scrape interval, push interval, Prometheus host/port)

- `docker/`  
  Image build context:
  - `docker/Dockerfile` (extends `aimilefth/base-monitoring-client`)
  - `docker/monitor_impl.py` (PyJoules collector + normalization)
  - `docker/docker_build.sh`

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

## Configuration (`cpu-pyjoules/.env`)

Key variables:

- `CLIENT_CPU_PROMETHEUS_HOST`  
  Where Prometheus is reachable from this client.  
  Same-machine default: `host.docker.internal`  
  Remote-machine: set to server public IP/DNS.

- `CLIENT_CPU_PROMETHEUS_PORT`  
  Prometheus host port (default `9090`)

- `CLIENT_CPU_SCRAPE_INTERVAL_S`  
  PyJoules measurement interval

- `CLIENT_CPU_PUSH_INTERVAL_S`  
  How often to push batches

- `CLIENT_CPU_MAX_RETRY_BATCHES`  
  How many failed batches to keep in memory while Prometheus is down

- `PRIVILEGED`  
  If `True`, the helper script will merge `docker-compose.privileged.yml`

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

Alternatively, set `PRIVILEGED=True` in `cpu-pyjoules/.env` and use the helper script — then `docker-compose.privileged.yml` will be merged and the service will run privileged.

---

## Running (via main compose)

With the repo helper:

```bash
./docker-compose-helper.sh -s cpu-pyjoules up -d
```

Or directly:

```bash
cd cpu-pyjoules
docker compose up -d
```

You should then see in Prometheus time series such as:

* `pyjoules_remote_write_energy_uj{component="package-0",source="cpu-pyjoules"}`
* `pyjoules_remote_write_energy_uj{component="core",source="cpu-pyjoules"}`
* `pyjoules_remote_write_energy_uj{component="uncore",source="cpu-pyjoules"}` (depending on the machine)

---

## Building the image

The Docker build context is `cpu-pyjoules/docker/`:

```bash
cd cpu-pyjoules/docker
./docker_build.sh
```

This builds/pushes `aimilefth/cpu-pyjoules` (as configured in the script).

---