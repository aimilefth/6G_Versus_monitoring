# PyJoules Metrics Client: Push-Based (Remote Write)

This prototype demonstrates the **push model** using Prometheus's remote write feature.

## Functionality

Unlike the pull model, this client actively pushes data to a Prometheus remote write endpoint. This is useful when the client should control the data transmission rate.

The client operates with two main threads:
1.  **Sampler:** A thread that collects power consumption data at a regular, high-frequency interval (`SAMPLING_PERIOD_S`).
2.  **Shipper:** A thread that collects data from the sampler, batches it into groups (`BATCH_SIZE`), serializes it into the efficient Protobuf format, compresses it, and sends it to Prometheus via an HTTP POST request.

- **Data Model:** Pushes raw energy consumption (in microjoules) with precise timestamps.
- **Collection Method:** Push. The client initiates the connection and sends data to Prometheus.
- **Data Rate:** The data ingestion rate is controlled entirely by the client's `SAMPLING_PERIOD_S` and `BATCH_SIZE` settings, independent of any Prometheus configuration.

## Code Explanation

### `remote_write_pusher.py`
This script orchestrates the sampling and pushing of data.
- **`sampler()` function:** Runs in a background thread. It periodically calls the `power_scraper`, converts the timestamp to milliseconds (as required by the remote write spec), and places the data into a shared thread-safe `queue`.
- **`shipper()` function:** Also runs in a background thread.
    1.  It pulls a `BATCH_SIZE` number of samples from the queue.
    2.  It groups the samples by their time series (i.e., by metric name and labels).
    3.  It constructs a `WriteRequest` object using the `remote_pb2` classes generated from the protobuf file.
    4.  It serializes the `WriteRequest` into a binary protobuf message.
    5.  It compresses the binary payload using `snappy`.
    6.  It sends the compressed payload in an HTTP POST request to the `REMOTE_WRITE_URL` with the required headers.
- **Main Execution:** The script starts both the `sampler` and `shipper` threads and then enters an idle loop to keep the container running.

### `remote.proto`
This is the Protocol Buffers (protobuf) definition file for the Prometheus remote write protocol. It defines the structure of the `WriteRequest`, `TimeSeries`, `Label`, and `Sample` messages. This file is used to generate the Python code (`remote_pb2.py`) needed for serialization.

### `Dockerfile`
- It uses a `python:3.11-slim` base image.
- **Build Process:**
    1.  It first installs all dependencies, including `grpcio-tools` for the protobuf compiler.
    2.  It copies the `remote.proto` file and runs the compiler to generate the necessary `remote_pb2.py` file.
    3.  It copies the application source code.
- **Environment Variables:**
    - `SAMPLING_PERIOD_S`: The interval for data collection.
    - `BATCH_SIZE`: The number of samples to batch together before sending.
    - `REMOTE_WRITE_URL`: The full URL to the Prometheus remote write endpoint. This is configured in the `docker-compose.yml` file to point to `http://prometheus:9090/api/v1/write`.