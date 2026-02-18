# server (Prometheus + Grafana stack)

This directory contains the **server-side monitoring stack**:

- **Prometheus** (time-series database + remote-write receiver)
- **Grafana** (visualization, pre-provisioned datasource + dashboard)

Client machines (e.g. `cpu-pyjoules/`) push metrics to Prometheus via the **host-exposed Prometheus port**.

---

## Directory layout

```text
server/
├── docker-compose.yml
├── .env
├── prometheus/
│   ├── entrypoint.sh
│   └── ...
└── grafana/
    ├── grafana.ini
    ├── provisioning/
    ├── dashboards/
    └── ...
```

---

## Services

### 1) Prometheus

* Image configured in `server/.env` (`PROMETHEUS_IMAGE`)
* Exposes port `PROMETHEUS_PORT` on the host (default `9090`)
* Generates `/etc/prometheus/prometheus.yml` at startup via `prometheus/entrypoint.sh`
* Runs with remote-write receiver enabled:

  * `--web.enable-remote-write-receiver`

Clients push to:

```
http://<server-host>:<PROMETHEUS_PORT>/api/v1/write
```

### 2) Grafana

* Image configured in `server/.env` (`GRAFANA_IMAGE`)
* Exposes port `GRAFANA_PORT` on the host (default `3000`)
* Uses provisioning files under `server/grafana/` to auto-configure:

  * Prometheus datasource (`http://prometheus:9090` inside the server network)
  * dashboard JSON(s) under `server/grafana/dashboards/`

---

## Configuration (`server/.env`)

Common variables:

* `PROMETHEUS_IMAGE`, `GRAFANA_IMAGE`
* `PROMETHEUS_PORT` (default `9090`)
* `GRAFANA_PORT` (default `3000`)
* `PROMETHEUS_SCRAPE_INTERVAL`, `PROMETHEUS_EVALUATE_INTERVAL`
* `UID`, `GID` (Grafana runs as this user for clean host volume permissions)

---

## Running

From the repo root (recommended), using the helper:

```bash
./docker-compose-helper.sh -s server up -d
```

Stopping:

```bash
./docker-compose-helper.sh -s server down
```

Or, run directly from this directory:

```bash
cd server
docker compose up -d
docker compose down
```

---

## Access

* Prometheus: `http://<server-host>:<PROMETHEUS_PORT>` (default `http://localhost:9090`)
* Grafana: `http://<server-host>:<GRAFANA_PORT>` (default `http://localhost:3000`)

Grafana credentials are configured in:

* `server/grafana/grafana.ini`

---

## Connecting clients

Client stacks (e.g. `cpu-pyjoules/`) should point to this server by setting in their `.env`:

* `CLIENT_CPU_PROMETHEUS_HOST=<server-hostname-or-ip>`
* `CLIENT_CPU_PROMETHEUS_PORT=<PROMETHEUS_PORT>` (usually `9090`)

On the same machine, clients often use:

* `CLIENT_CPU_PROMETHEUS_HOST=host.docker.internal`
