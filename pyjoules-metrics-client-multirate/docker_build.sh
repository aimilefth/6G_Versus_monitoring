#!/bin/bash
docker build -t aimilefth/pyjoules-metrics-client-multirate --push . 2>&1 | tee build.log