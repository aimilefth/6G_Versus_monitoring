#!/bin/sh
set -eu

# -------- defaults (can be overridden from .env / compose) ----------
: "${PROMETHEUS_SCRAPE_INTERVAL:=2}"
: "${PROMETHEUS_EVAL_INTERVAL:=1}"
: "${PROMETHEUS_TARGET:=prometheus:9090}"
: "${CLIENT_SIMPLE_EXPORTER_PORT:=9091}"
: "${CLIENT_MULTIRATE_EXPORTER_PORT:=9092}"

# -------- write out the real config file -----------------------------
cat > /etc/prometheus/prometheus.yml <<EOF
global:
  scrape_interval: ${PROMETHEUS_SCRAPE_INTERVAL}s
  evaluation_interval: ${PROMETHEUS_EVAL_INTERVAL}s

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["${PROMETHEUS_TARGET}"]

  - job_name: "pyjoules_simple"
    static_configs:
      - targets: ["pyjoules-metrics-client-simple:${CLIENT_SIMPLE_EXPORTER_PORT}"]

  - job_name: "pyjoules_multirate"
    static_configs:
      - targets: ["pyjoules-metrics-client-multirate:${CLIENT_MULTIRATE_EXPORTER_PORT}"]
EOF

# -------- start prometheus ------------------------------------------
exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --web.enable-remote-write-receiver
