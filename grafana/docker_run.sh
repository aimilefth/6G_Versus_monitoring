#!/bin/bash

GRAFANA_STORAGE_PATH="$(pwd)/grafana-storage"

docker run --name grafana \
  -d \
  --network=host \
  --user "$(id -u):$(id -g)" \
  -v "${GRAFANA_STORAGE_PATH}:/var/lib/grafana" \
  --pull=always \
  grafana/grafana:12.0.2

echo "Grafana container started."
echo "Access the Grafana UI at http://localhost:3000"