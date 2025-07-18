# Prometheus Docker Setup

This directory contains:

- `prometheus.yml`: your Prometheus configuration file
- `README.md`: this file

---

## Running Prometheus in Docker

You can start Prometheus in a Docker container, mounting your local `prometheus.yml` into the container and publishing port **9090**.

```bash
cd /path/to/6G_Versus_monitoring/prometheus

docker run --name prometheus \
  -d \
  -p 9090:9090 \
  -v "$(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml" \
  prom/prometheus:v3.5.0
