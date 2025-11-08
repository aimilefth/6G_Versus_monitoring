#!/bin/bash

# Run the pyJoules client container
docker run --name pyjoules-metrics-client-simple \
  -d \
  --network=host \
  --privileged \
  --pull=always \
  aimilefth/pyjoules-metrics-client-simple

echo "pyJoules metrics client container started."
echo "Metrics will be available at http://localhost:9091/metrics after a few seconds."
echo "Note: The container is running in privileged mode to allow pyJoules access to MSR."