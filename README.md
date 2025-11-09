# Power Consumption Monitoring with Prometheus, Grafana, and PyJoules

This project provides a complete, containerized monitoring infrastructure for capturing, storing, and visualizing power consumption metrics from x86 systems using [PyJoules](https://github.com/powerapi-ng/pyJoules).

Following a significant refactor, the project now demonstrates a robust and modular **push-based (Remote Write)** architecture. This design decouples the monitoring clients from the Prometheus server, allowing them to collect data at a high frequency and push it efficiently in batches.


## Architectural Overview

The new architecture is designed for extensibility and clarity:

1.  **`base-monitoring-client`**: A generic base Docker image that contains all the core logic for a robust remote-write client. It manages a multi-threaded pipeline for data collection, processing, batching, and pushing to Prometheus, complete with a retry mechanism for network resilience.
2.  **`cpu-pyjoules`**: A concrete monitoring client that extends the `base-monitoring-client`. It provides the specific implementation for gathering CPU power data using the `pyJoules` library. New clients for different metrics (e.g., GPU, system stats) can be easily created by following this pattern.
3.  **Prometheus**: The central time-series database, configured to accept data via its remote-write endpoint. It no longer actively scrapes the monitoring clients.
4.  **Grafana**: The visualization platform, pre-configured with a dashboard to display the power consumption data stored in Prometheus.

This modular approach separates the generic "how to send data" logic from the specific "what data to collect" logic, making the system cleaner and easier to maintain.

---

## Project Structure

```text
.
├── AppArmor/                 # custom profile to let a container read RAPL
├── base-monitoring-client/   # generic remote-write client (pushes to Prometheus)
├── cpu-pyjoules/             # concrete pyJoules-based monitoring client
├── grafana/                  # preprovisioned dashboard + datasource
├── prometheus/               # dynamic entrypoint, remote-write enabled
├── docker-compose.yml
├── docker-compose.privileged.yml
├── docker-compose_helper.sh  # wrapper that decides privileged vs AppArmor
├── .env                      # central configuration
└── README.md                 # this file
```
---

## Services

### 1. Prometheus

* Image: configurable via `.env` (`PROMETHEUS_IMAGE=prom/prometheus:v3.5.0`)
* Generates its `prometheus.yml` at startup from env vars.
* Exposes `:9090` on the host.
* **Remote-write receiver enabled** so clients can push.

### 2. Grafana

* Image: configurable via `.env`
* Preprovisioned datasource + dashboard under `grafana/`.
* Exposes `:3000` on the host.
* Runs as the UID/GID from `.env` so you can persist data on the host.

### 3. `cpu-pyjoules`

* Image: `aimilefth/cpu-pyjoules` (built from `cpu-pyjoules/`)
* Inherits from `aimilefth/base-monitoring-client`
* Reads RAPL from the host under `/sys/.../powercap/...`
* Pushes remote-write data to Prometheus
* Labeled in metrics as `source="cpu-pyjoules"`

---

## The data flow

1. **`cpu-pyjoules`** (container) runs two threads:

   * **collector**: uses pyJoules every `SCRAPE_INTERVAL_S` to read energy,
   * **processor**: currently pass-through.
2. 2. The **cpu-pyjoules client’s `process_data()`** converts the pyJoules dictionaries into normalized Prometheus records (one time series per energy domain). The **base monitoring client** then just batches and remote-writes them.
3. Every `PUSH_INTERVAL_S` seconds the client **pushes** a remote-write batch to Prometheus.
4. Prometheus stores it, Grafana displays it.

---

## Configuration

Everything lives in `.env`:

Key ones:

* **`CLIENT_CPU_PYJOULES_URL`**: where to remote-write (inside Docker network, so `http://prometheus:9090/...`).
* **`CLIENT_CPU_PYJOULES_SCRAPE_INTERVAL_S`**: how often pyJoules samples (inside the container).
* **`CLIENT_CPU_PYJOULES_PUSH_INTERVAL_S`**: how often the client sends a remote-write batch.
* **`PRIVILEGED`**: if set to `True`/`true` in `.env`, the helper will add `docker-compose.privileged.yml`, otherwise we rely on AppArmor.

## Running

We now recommend using the helper script because it respects `.env` and the privileged toggle:

```bash
./docker-compose_helper.sh up -d
```

This will:

* create the `monitoring` network,
* start Prometheus,
* start Grafana,
* start `cpu-pyjoules` with the right AppArmor profile (or privileged, depending on `.env`).

To stop:

```bash
./docker-compose_helper.sh down
```

---

## Host requirements

* Docker / Docker Compose plugin
* A host that actually exposes power/energy counters under:

  * `/sys/class/powercap`
  * `/sys/devices/virtual/powercap`
* Either:

  * run the client **privileged** (`PRIVILEGED=True`), **or**
  * install the provided AppArmor profile:

    ```bash
    cd AppArmor
    sudo ./setup_docker-pyjoules.sh
    ```

  and keep this in your `docker-compose.yml` (already present):

  ```yaml
  security_opt:
    - apparmor=docker-pyjoules
    - systempaths=unconfined
  ```

---

## Extending the stack

The point of `base-monitoring-client/` is that you can build a *different* monitoring container with almost no code:

1. Create a new directory (e.g. `gpu-telem/`).

2. `FROM aimilefth/base-monitoring-client:latest`

3. COPY your own `monitor_impl.py` that implements:

   ```python
   def get_power(output_queue, scrape_interval_s, stop_event): ...
   def process_data(input_queue, output_queue, stop_event): ...
   ```

4. Add a service to `docker-compose.yml` with the right volumes/envs.

5. It will push to Prometheus automatically.

---

## Metrics you’ll see

By default the client emits **one time series per energy domain**, for example:

* `pyjoules_remote_write_energy_uj{component="package-0",source="cpu-pyjoules"}`
* `pyjoules_remote_write_energy_uj{component="core",source="cpu-pyjoules"}`

Use those in Prometheus/Grafana queries.

---