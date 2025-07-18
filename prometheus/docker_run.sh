#!/bin/bash

PROMETHEUS_CONFIG_PATH="$(pwd)/prometheus.yml"

docker run --name prometheus \
  -d \
  --network=host \
  -v "${PROMETHEUS_CONFIG_PATH}:/etc/prometheus/prometheus.yml" \
  --pull=always \
  prom/prometheus:v3.5.0

echo "Prometheus container started."
echo "Access the Prometheus UI at http://localhost:9090"