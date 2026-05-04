# xavier-nx-jtop

This client stack runs on NVIDIA Jetson AGX orin and pushes jtop / jetson-stats
metrics to Prometheus via Remote Write using the shared `base-monitoring-client`
runtime.

Unlike the `agx-orin` INA3221 power client, this one reads host telemetry
through the `jetson-stats` Python API.

## Important Docker requirement

`jtop` in Docker needs the host `jtop.service`.

On the Xavier NX host:

```bash
sudo pip3 install -U jetson-stats
sudo systemctl restart jtop.service
sudo systemctl status jtop.service
````

The container also installs `jetson-stats`, and `docker-compose.yml` mounts:

```yaml
volumes:
  - /run/jtop.sock:/run/jtop.sock
```

If the socket is group-restricted, set:

```bash
export JTOP_GID="$(getent group jtop | awk -F: '{print $3}')"
```

or put the numeric value in `.env`.

## Metrics emitted

Defaults:

```text
xavier_nx_cpu_util_percent{component="cpu0",source="xavier-nx-jtop-01"}
xavier_nx_cpu_freq_khz{component="cpu0",source="xavier-nx-jtop-01"}
xavier_nx_memory_util_percent{component="RAM",source="xavier-nx-jtop-01"}
xavier_nx_gpu_util_percent{component="gpu",source="xavier-nx-jtop-01"}
xavier_nx_thermal_celsius{component="CPU",source="xavier-nx-jtop-01"}
```

Metric names can be overridden with:

```dotenv
METRIC_CPU_UTIL=...
METRIC_CPU_FREQ=...
METRIC_MEMORY_UTIL=...
METRIC_GPU_UTIL=...
METRIC_THERMAL=...
```

## Enable / disable collectors

In `.env`:

```dotenv
ENABLE_CPU_UTIL=true
ENABLE_CPU_FREQ=true
ENABLE_MEMORY_UTIL=true
ENABLE_GPU_UTIL=true
ENABLE_THERMAL=true
```

You can also make expensive collectors run less often:

```dotenv
THERMAL_INTERVAL_S=2
GPU_UTIL_INTERVAL_S=1
```

A value of `0` means "run every jtop sample".

## Build

```bash
cd xavier-nx-jtop/docker
./docker_build.sh
```

## Run

From repo root:

```bash
./docker-compose-helper.sh -s xavier-nx-jtop up -d
```

Logs:

```bash
./docker-compose-helper.sh -s xavier-nx-jtop logs -f
```

## Example PromQL

CPU utilization per core:

```promql
xavier_nx_cpu_util_percent{source="xavier-nx-jtop-01"}
```

CPU frequency per core:

```promql
xavier_nx_cpu_freq_khz{source="xavier-nx-jtop-01"}
```

Memory utilization:

```promql
xavier_nx_memory_util_percent{source="xavier-nx-jtop-01"}
```

GPU utilization:

```promql
xavier_nx_gpu_util_percent{source="xavier-nx-jtop-01"}
```

Thermals:

```promql
xavier_nx_thermal_celsius{source="xavier-nx-jtop-01"}
```

````

---

Run it with:

```bash
./docker-compose-helper.sh -s xavier-nx-jtop up -d
````

And verify in Prometheus with:

```promql
{source="xavier-nx-jtop-01"}
```