#!/bin/bash
docker build -t aimilefth/pyjoules-metrics-client-remote-write --push . 2>&1 | tee build.log