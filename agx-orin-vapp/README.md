


# agx-orin-vapp

`agx-orin-vapp` is a monitoring client that runs on the x86 server and extends `base-monitoring-client`.

It reads recent AGX Orin telemetry from Prometheus, groups all metric/component samples that share the same timestamp into one model input row, calls `model(data)`, and writes the returned `calibrated_power` values back to Prometheus through remote write.

## What it reads

By default, it reads AGX Orin jtop metrics from:

```promql
{source=~"agx-orin-jtop-01",__name__=~"agx_orin_.*"}[3s]
````

The input source and metric selectors are controlled by `.env`:

```dotenv
CLIENT_AGX_ORIN_VAPP_INPUT_SOURCE_REGEX=agx-orin-jtop-01
CLIENT_AGX_ORIN_VAPP_INPUT_METRIC_REGEX=agx_orin_.*
```

## What it writes

The service writes this output metric:

```promql
agx_orin_vapp_calibrated_power_watts{source="agx-orin-vapp-01",component="calibrated_power",input_source="agx-orin-jtop-01",model="default"}
```

## Timestamp handling

The service fetches more data than one scrape interval to avoid losing samples.

With the current `.env`:

```dotenv
CLIENT_AGX_ORIN_VAPP_SCRAPE_INTERVAL_S=2
CLIENT_AGX_ORIN_VAPP_FETCH_LOOKBACK_S=4
CLIENT_AGX_ORIN_VAPP_EMIT_DELAY_S=1
```

This means it queries every 2 seconds, but each query looks back 4 seconds. It also waits 1 second before emitting the newest timestamp, so Prometheus has time to receive all metrics for that timestamp.

The service stores the last emitted timestamp in:

```text
/data/agx-orin-vapp-state.json
```

That file is persisted through the compose volume:

```yaml
../data/agx-orin-vapp:/data
```

## Model input

`docker/model.py` receives one row per timestamp:

```python
{
    "timestamp_ms": 1777969625405,
    "timestamp_iso": "2026-05-05T08:27:05.405000Z",
    "features": {
        "agx_orin_cpu_util_percent__cpu0": 10.0,
        "agx_orin_cpu_freq_mhz__cpu0": 729.6,
        "agx_orin_power_watts__total": 7.028
    },
    "labels": {
        "input_source": "agx-orin-jtop-01"
    }
}
```

`model(data)` should return either:

```python
[
    {"timestamp_ms": row["timestamp_ms"], "calibrated_power": 7.25},
    ...
]
```

or a simple list aligned with input rows:

```python
[7.25, 7.31, 7.28]
```

## Build

From the service Docker directory:

```bash
cd agx-orin-vapp/docker
./docker_build.sh
```

## Run

From the repository root:

```bash
bash docker-compose-helper.sh -s agx-orin-vapp up -d
```

## Logs

```bash
bash docker-compose-helper.sh -s agx-orin-vapp logs -f
```

## Stop

```bash
bash docker-compose-helper.sh -s agx-orin-vapp down
```

## Verify output in Prometheus

Use this PromQL query:

```promql
agx_orin_vapp_calibrated_power_watts{source="agx-orin-vapp-01"}
```

To verify the input data exists:

```promql
{source="agx-orin-jtop-01",__name__=~"agx_orin_.*"}
```
