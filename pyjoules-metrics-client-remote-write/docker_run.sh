#!/bin/bash

# Run the pyJoules client container
docker run \ --name pyjoules-metrics-client-remote-write \
  -d \
  --network=host \
  --privileged \
  --pull=always \
  aimilefth/pyjoules-metrics-client-remote-write
