# agx-orin (Jetson AGX Orin client stack)

This client stack runs on **NVIDIA Jetson AGX Orin** (ARM64) and pushes power metrics to Prometheus via **Remote Write** using the shared `base-monitoring-client` runtime.

It reads rail telemetry from the INA3221 sysfs entries documented by NVIDIA and emits normalized Prometheus records.

## What it emits

This client produces three metrics by default:

- `agx_orin_power_watts{component="VDD_GPU_SOC",source="agx-orin"}`
- `agx_orin_voltage_volts{component="VDD_GPU_SOC",source="agx-orin"}`
- `agx_orin_current_amps{component="VDD_GPU_SOC",source="agx-orin"}`

And also a total:

- `agx_orin_power_watts{component="total",source="agx-orin"}`

Metric names can be overridden via env:
- `METRIC_POWER_W`, `METRIC_VOLTAGE_V`, `METRIC_CURRENT_A`

## Files

```

agx-orin/
├── docker-compose.yml
├── README.md
└── docker/
├── Dockerfile
├── docker_build.sh
└── monitor_impl.py

````

## Configuration

You can pass variables either by exporting them in your shell or by creating an optional `.env` file next to `docker-compose.yml`.

Main variables:

- `CLIENT_AGX_PROMETHEUS_HOST` (default: `host.docker.internal`)
- `CLIENT_AGX_PROMETHEUS_PORT` (default: `9090`)
- `CLIENT_AGX_SCRAPE_INTERVAL_S` (default: `0.2`)
- `CLIENT_AGX_PUSH_INTERVAL_S` (default: `4`)
- `CLIENT_AGX_MAX_RETRY_BATCHES` (default: `5`)
- `CLIENT_AGX_LOG_LEVEL` (default: `INFO`)
- `CLIENT_AGX_SERVICE_LABEL` (default: `agx-orin`)


## Build the image

On your build machine (or directly on the Orin):

```bash
cd agx-orin/docker
./docker_build.sh
````

This builds and pushes an **ARM64** image by default:

* `aimilefth/agx-orin`

You can override the image name:

```bash
IMAGE_NAME=myrepo/agx-orin ./docker_build.sh
```

## Run

From the repo root, you can run with your helper (it just `cd`s into the directory):

```bash
./docker-compose-helper.sh -s agx-orin up -d
```

Or run directly:

```bash
cd agx-orin
docker compose up -d
```

## Notes & troubleshooting

### 1) Sysfs path differences

The implementation reads:

* `/sys/bus/i2c/drivers/ina3221/1-004*/hwmon/hwmon*/in*_input`
* `/sys/bus/i2c/drivers/ina3221/1-004*/hwmon/hwmon*/curr*_input`

If your Jetson exposes a different path (driver name, bus number, or device address), adjust `docker/monitor_impl.py` accordingly.