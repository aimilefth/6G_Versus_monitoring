# PyJoules Metrics Client: Simple Pull-Based Exporter

This prototype demonstrates the most common method of Prometheus monitoring: the **pull model**.

## Functionality

The client operates as a simple metric exporter. It continuously measures power consumption and exposes the latest reading as a set of Prometheus metrics on an HTTP endpoint. Prometheus is configured to "scrape" (fetch data from) this endpoint at a regular interval.

- **Data Model:** The client calculates the average power consumption (in Watts) over its internal measurement interval.
- **Collection Method:** Passive. The client waits for Prometheus to request data.
- **Data Rate:** The rate of data ingestion into Prometheus is determined entirely by Prometheus's `scrape_interval`.

## Code Explanation

### `prometheus_client_exporter.py`
This is the main script that runs the exporter.
- **Metrics Definition:** It uses the `prometheus-client` library to define two `Gauge` metrics:
    - `pyjoules_simple_energy_watts`: Stores the calculated power in Watts, with a `domain` label (e.g., `core`, `dram`).
    - `pyjoules_simple_measurement_duration_seconds`: Stores the duration of each measurement cycle.
- **`MetricsExporter` Class:**
    - The `run_metrics_loop` method runs in a background thread.
    - Inside its loop, it calls `power_scraper.get_power()` to get a new energy measurement.
    - It calculates the average power in Watts by dividing the energy (Joules) by the measurement duration (seconds).
    - It updates the Prometheus `Gauge` objects with the new values using `.set()`.
- **Main Function:**
    - It starts the Prometheus HTTP server on the port specified by the `EXPORTER_PORT` environment variable (default: 9091).
    - It starts the `run_metrics_loop` in a daemon thread.

### `power_scraper.py`
This is a helper module that provides a clean interface to the `pyJoules` library. The `power_scraper` class has a `get_power()` method that performs a single energy measurement over a specified interval and returns the data as a dictionary.

### `Dockerfile`
- It uses a lightweight `python:3.11-slim` base image.
- It installs the necessary, version-pinned Python dependencies: `pyjoules==0.5.1` and `prometheus-client==0.23.1`.
- It copies the application source code into the container.
- It defines default environment variables that can be overridden in `docker-compose.yml`:
    - `EXPORTER_PORT=9091`: The port on which the `/metrics` endpoint will be exposed.
    - `SCRAPE_INTERVAL_SECONDS=0.1`: The internal measurement interval for `pyJoules`.
- The `CMD` instruction starts the exporter script when the container runs.