#!/bin/bash
docker build -t aimilefth/pyjoules-metrics-client-simple --push . 2>&1 | tee build.log