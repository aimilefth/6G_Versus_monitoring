# Power Consumption Monitoring with Prometheus, Grafana, and PyJoules

This project provides a complete, containerized monitoring infrastructure for capturing, storing, and visualizing power consumption metrics from x86 systems using [PyJoules](https://github.com/powerapi-ng/pyJoules).

The architecture is **push-based (Prometheus Remote Write)**: monitoring clients collect at high frequency and **push** batches to a Prometheus server. Grafana reads from Prometheus for dashboards.


## Architectural Overview

The repo is split into **stacks** so you can deploy:

- a **server stack** (Prometheus + Grafana) on one machine, and
- multiple **client stacks** (CPU, GPU, etc.) on many machines.

Core components:

1. **`base-monitoring-client/`**  
   A generic remote-write client runtime:
   - runs worker threads from a `monitor_impl.py`,
   - batches normalized records,
   - pushes them to Prometheus with retry logic.

2. **Client stacks** (first one: `cpu-pyjoules/`)  
   Each client stack:
   - ships its own `docker-compose.yml` + `.env`,
   - defines where Prometheus is reachable “from the outside”,
   - optionally runs privileged or under AppArmor.

3. **`server/`**  
   Runs:
   - **Prometheus** with remote-write receiver enabled,
   - **Grafana** with a pre-provisioned datasource + dashboard.

This modular approach separates the generic "how to send data" logic from the specific "what data to collect" logic, making the system cleaner and easier to maintain.

---

## Project Structure

```text
.
├── AppArmor/                 # custom profile to let a container read RAPL
├── base-monitoring-client/   # generic remote-write client (pushes to Prometheus)
├── cpu-pyjoules/             # The specific client logic for PyJoules
│   ├── docker/               # Dockerfile and Python implementation for this client
│   └── ...                   # Docker Compose files
├── server/ 
│   ├── grafana/              # preprovisioned dashboard + datasource
│   ├── prometheus/           # dynamic entrypoint, remote-write enabled
    └── ...                   # Docker Compose files
├── docker-compose-helper.sh  # run one or more stacks with -s flags
└── README.md                 # this file
```
---

## Stacks and configuration

### 1) `server/` (Prometheus + Grafana)

* `server/docker-compose.yml`
* `server/.env`
* Prometheus listens on the host port (`PROMETHEUS_PORT`, default 9090)
* Grafana listens on the host port (`GRAFANA_PORT`, default 3000)

### 2) `cpu-pyjoules/` (CPU client)

* `cpu-pyjoules/docker-compose.yml`
* `cpu-pyjoules/.env`
* Pushes to Prometheus via a host-reachable address:

  * `CLIENT_CPU_PROMETHEUS_HOST`
  * `CLIENT_CPU_PROMETHEUS_PORT`

### 3. `cpu-pyjoules`

* Image: `aimilefth/cpu-pyjoules` (built from `cpu-pyjoules/`)
* Inherits from `aimilefth/base-monitoring-client`
* Reads RAPL from the host under `/sys/.../powercap/...`
* Pushes remote-write data to Prometheus
* Labeled in metrics as `source="cpu-pyjoules"`

If you rebuild the images yourself, the provided `docker_build.sh` in `base-monitoring-client/` is already set up to use `docker buildx build` and push a multi-platform image (`linux/amd64`, `linux/arm64`). Therefore you need to install [`Docker buildx`](https://github.com/docker/buildx).

---

### The data flow

1. **`cpu-pyjoules`** (container) runs two threads:

   * **collector**: uses pyJoules every `SCRAPE_INTERVAL_S` to read energy,
   * **processor**: currently pass-through.
2. 2. The **cpu-pyjoules client’s `process_data()`** converts the pyJoules dictionaries into normalized Prometheus records (one time series per energy domain). The **base monitoring client** then just batches and remote-writes them.
3. Every `PUSH_INTERVAL_S` seconds the client **pushes** a remote-write batch to Prometheus.
4. Prometheus stores it, Grafana displays it.

---

### Configuration

Everything lives in the respective stack's `.env`:

Key ones:

* **`CLIENT_CPU_PYJOULES_URL`**: where to remote-write (inside Docker network, so `http://prometheus:9090/...`).
* **`CLIENT_CPU_PYJOULES_SCRAPE_INTERVAL_S`**: how often pyJoules samples (inside the container).
* **`CLIENT_CPU_PYJOULES_PUSH_INTERVAL_S`**: how often the client sends a remote-write batch.
* **`PRIVILEGED`**: if set to `True`/`true` in `.env`, the helper will add `docker-compose.privileged.yml`, otherwise we rely on AppArmor.

## Running

This repo includes a helper that can start/stop multiple stacks:

```bash
./docker-compose-helper.sh -s server up -d
./docker-compose-helper.sh -s cpu-pyjoules up -d
./docker-compose-helper.sh -s server -s cpu-pyjoules up -d
```

Stopping:

```bash
./docker-compose-helper.sh -s server -s cpu-pyjoules down
```

The helper `cd`s into each stack directory and runs `docker compose` there, so each stack uses its local `.env`.

---

## Deploying clients to other machines

To move a client to another host:

1. Clone this repo on the client machine.
2. Edit `cpu-pyjoules/.env`:

   * set `CLIENT_CPU_PROMETHEUS_HOST` to the server’s public IP/DNS
   * keep `CLIENT_CPU_PROMETHEUS_PORT` the exposed Prometheus port (default 9090)
3. Run only that client stack:

```bash
./docker-compose-helper.sh -s cpu-pyjoules up -d
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

1. Create a new stack directory (e.g. `gpu-smi/`) with:

   * `docker-compose.yml`
   * `.env`

2. Create a `docker/` subdir for its image build:

   * `docker/Dockerfile` based on `aimilefth/base-monitoring-client:latest`
   * `docker/monitor_impl.py` implementing:

     ```python
     def get_power(output_queue, scrape_interval_s, stop_event): ...
     def process_data(input_queue, output_queue, stop_event): ...

---

## Metrics you’ll see

By default the client emits **one time series per energy domain**, for example:

* `pyjoules_remote_write_energy_uj{component="package-0",source="cpu-pyjoules"}`
* `pyjoules_remote_write_energy_uj{component="core",source="cpu-pyjoules"}`

Use those in Prometheus/Grafana queries.

---