# PyJoules Metrics Client: Multirate Pull-Based Exporter

This prototype demonstrates an advanced **pull model** designed to capture high-frequency data without requiring Prometheus to scrape at the same high frequency.

## Functionality

This client solves the challenge of measuring power at a high rate (e.g., every 100ms) when Prometheus can only scrape less frequently (e.g., every 2s).

1.  **High-Frequency Internal Sampling:** A background thread samples power consumption at a high rate, as defined by `SCRAPE_INTERVAL_SECONDS`.
2.  **Buffering:** Each sample, with its precise timestamp, is stored in an in-memory buffer (`deque`).
3.  **Batched Export:** When Prometheus scrapes the client, the client provides the *entire buffer* of samples. Because each sample has its original timestamp, Prometheus can import them correctly, effectively backfilling the high-resolution data.

- **Data Model:** The client exports the raw energy consumption (in microjoules) for each sample.
- **Collection Method:** Advanced pull. The client actively samples at a high rate and provides a batch of data on each pull.
- **Data Rate:** The client decouples the sampling rate from the Prometheus scrape rate.

## Code Explanation

### `prometheus_client_exporter.py`
- **`sampler(buffer, period)` function:** This function runs in a dedicated background thread. It has a simple loop that calls the `power_scraper`, gets a measurement, attaches a UTC timestamp, and appends the result to the shared `ring_buffer`. It respects the `MAX_QUEUE_LEN` to prevent unbounded memory growth.
- **`PowerCollector` Class:** This is a custom Prometheus collector that implements the `collect()` method.
    - This method is invoked by the `prometheus-client` library *only when a scrape occurs*.
    - It drains the shared `ring_buffer`, taking all the samples that have accumulated.
    - For each sample, it creates Prometheus `Metric` objects, crucially assigning the sample's **original timestamp** to the `timestamp` field. This tells Prometheus to record the value at that specific point in time, not at the time of the scrape.
- **Main Function:**
    - It registers the custom `PowerCollector`.
    - It starts the Prometheus HTTP server (default port: 9092).
    - It starts the `sampler` function in a daemon thread.

### `Dockerfile`
- It uses a lightweight `python:3.11-slim` base image.
- It installs version-pinned dependencies: `pyjoules==0.5.1` and `prometheus-client==0.23.1`.
- Defines three environment variables to control its behavior:
    - `EXPORTER_PORT=9092`: The port for the `/metrics` endpoint.
    - `SCRAPE_INTERVAL_SECONDS=0.1`: The internal high-frequency sampling rate (10 times per second).
    - `MAX_QUEUE_LEN=1000`: The maximum number of samples to buffer (a safety measure).