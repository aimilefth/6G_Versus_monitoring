# orin-nx (Jetson Orin NX client stack)

This client stack runs on **NVIDIA Jetson Orin NX** (ARM64) and pushes power metrics to Prometheus via **Remote Write** using the shared `base-monitoring-client` runtime.

It reads rail telemetry from the INA3221 sysfs entries documented by NVIDIA and emits normalized Prometheus records.

## What it emits

This client produces three metrics by default:

- `agx_orin_power_watts{component="VDD_IN",source="orin-nx"}`
- `agx_orin_voltage_volts{component="VDD_IN",source="orin-nx"}`
- `agx_orin_current_amps{component="VDD_IN",source="orin-nx"}`

Metric names can be overridden via env:
- `METRIC_POWER_W`, `METRIC_VOLTAGE_V`, `METRIC_CURRENT_A`

The metrics are described on the [NVIDIA Jetson Linux Developer](https://docs.nvidia.com/jetson/archives/r36.4.3/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html#jetson-orin-nx-series-and-jetson-orin-nano-series)

## Files

```

orin-nx/
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

- `CLIENT_ORIN_NX_PROMETHEUS_HOST` (default: `host.docker.internal`)
- `CLIENT_ORIN_NX_PROMETHEUS_PORT` (default: `9090`)
- `CLIENT_ORIN_NX_SCRAPE_INTERVAL_S` (default: `0.2`)
- `CLIENT_ORIN_NX_PUSH_INTERVAL_S` (default: `4`)
- `CLIENT_ORIN_NX_MAX_RETRY_BATCHES` (default: `5`)
- `CLIENT_ORIN_NX_LOG_LEVEL` (default: `INFO`)
- `CLIENT_ORIN_NX_SERVICE_LABEL` (default: `orin-nx`)


## Build the image

On your build machine (or directly on the Orin):

```bash
cd orin-nx/docker
./docker_build.sh
````

This builds and pushes an **ARM64** image by default:

* `aimilefth/6gversus-monitoring:orin-nx`

You can override the image name:

```bash
IMAGE_NAME=myrepo/orin-nx ./docker_build.sh
```

## Run

From the repo root, you can run with your helper (it just `cd`s into the directory):

```bash
./docker-compose-helper.sh -s orin-nx up -d
```

Or run directly:

```bash
cd orin-nx
docker compose up -d
```

## Notes & troubleshooting

### 1) Sysfs path differences

The implementation reads:

* `/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon*/in*_input`
* `/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon*/curr*_input`

If your Jetson exposes a different path (driver name, bus number, or device address), adjust `docker/monitor_impl.py` accordingly.