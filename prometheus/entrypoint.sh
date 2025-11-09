#!/bin/sh
set -eu

# -------- defaults (can be overridden from .env / compose) ----------
: "${PROMETHEUS_SCRAPE_INTERVAL:=2}"
: "${PROMETHEUS_EVALUATE_INTERVAL:=1}"
: "${PROMETHEUS_TARGET:=prometheus:9090}"

# -------- write out the real config file -----------------------------
cat > /etc/prometheus/prometheus.yml <<EOF
global:
  scrape_interval: ${PROMETHEUS_SCRAPE_INTERVAL}s
  evaluation_interval: ${PROMETHEUS_EVALUATE_INTERVAL}s

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["${PROMETHEUS_TARGET}"]
EOF

# -------- start prometheus ------------------------------------------
exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --web.enable-remote-write-receiver
