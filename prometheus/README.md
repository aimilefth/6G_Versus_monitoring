# Prometheus Service

This directory contains the configuration for the Prometheus service.

## Role in the Project

Prometheus serves as the core of the monitoring stack. It is a powerful open-source monitoring and alerting toolkit that collects and stores its metrics as time-series data.

In this project, its key responsibilities are:
1.  **Data Storage:** Acting as the central database for all power consumption metrics collected by the PyJoules clients.
2.  **Data Collection (Pull):** Periodically "scraping" the HTTP `/metrics` endpoints exposed by the `pyjoules-metrics-client-simple` and `pyjoules-metrics-client-multirate` services to pull in new data.
3.  **Data Reception (Push):** Receiving data pushed from the `pyjoules-metrics-client-remote-write` service via the remote write API.
4.  **Data Source for Grafana:** Providing the stored time-series data to Grafana for visualization and analysis.

## Service Configuration

### `docker-compose.yml`

The Prometheus service is defined in the main `docker-compose.yml` file with the following key settings:
- **`image: ${PROMETHEUS_IMAGE}`**: Specifies the official Prometheus Docker image, configured via the `.env` file.
- **`networks: - monitoring`**: Connects Prometheus to the custom bridge network, allowing it to communicate with other services using their service names.
- **`volumes`**: The local `prometheus.yml` configuration file is mounted into the container at `/etc/prometheus/prometheus.yml`.
- **`command`**:
    - `--config.file=/etc/prometheus/prometheus.yml`: Tells Prometheus where to find its configuration file.
    - `--web.enable-remote-write-receiver`: Activates the endpoint that allows clients to push data directly to Prometheus.

### `prometheus.yml`

This file defines what and how Prometheus should monitor.
- **`global.scrape_interval: 2s`**: Sets the default frequency for scraping targets.
- **`scrape_configs`**: This section defines the monitoring jobs.
    - **`job_name: "prometheus"`**: The first job is for Prometheus to monitor itself, using its service name `prometheus:9090`.
    - **`job_name: "pyjoules_simple"`**: This job tells Prometheus to scrape our simple client. The target is `pyjoules-metrics-client-simple:9091`, using Docker's internal DNS to resolve the service name to the correct container IP.
    - **`job_name: "pyjoules_multirate"`**: This job defines the scraping configuration for the multirate client, available at `pyjoules-metrics-client-multirate:9092`.