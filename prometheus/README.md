# Prometheus Service

This directory contains the configuration and startup scripts for the Prometheus service.

## Role in the Project

Prometheus serves as the core of the monitoring stack. It is a powerful open-source monitoring and alerting toolkit that collects and stores its metrics as time-series data.

In this project, its key responsibilities are:
1.  **Data Storage:** Acting as the central database for all power consumption metrics collected by the PyJoules clients.
2.  **Data Collection (Pull):** Periodically "scraping" the HTTP endpoints (`/metrics`) exposed by the `pyjoules-metrics-client-simple` and `pyjoules-metrics-client-multirate` services to pull in new data.
3.  **Data Reception (Push):** Receiving data pushed from the `pyjoules-metrics-client-remote-write` service via the remote write API.
4.  **Data Source for Grafana:** Providing the stored time-series data to Grafana for visualization and analysis.

## Service Configuration

### `docker-compose.yml`

The Prometheus service is defined in the main `docker-compose.yml` file with the following key settings:
- **`image: prom/prometheus:v3.5.0`**: Specifies the official Prometheus Docker image.
- **`network_mode: host`**: Prometheus runs directly on the host's network. This simplifies the configuration, as it can scrape other services running on `localhost` at their respective ports.
- **`volumes`**: The local `prometheus.yml` configuration file is mounted into the container at `/etc/prometheus/prometheus.yml`, allowing Prometheus to use our custom settings.
- **`command`**:
    - `--config.file=/etc/prometheus/prometheus.yml`: Tells Prometheus where to find its configuration file inside the container.
    - `--web.enable-remote-write-receiver`: This crucial flag activates the endpoint (`/api/v1/write`) that allows clients like our `remote-write` prototype to push data directly to Prometheus.

### `prometheus.yml`

This file defines what and how Prometheus should monitor.
- **`global.scrape_interval: 2s`**: Sets the default frequency for scraping targets. Prometheus will poll the pull-based clients every two seconds.
- **`scrape_configs`**: This section defines the monitoring jobs.
    - **`job_name: "prometheus"`**: The first job is for Prometheus to monitor itself.
    - **`job_name: "pyjoules_simple"`**: This job tells Prometheus to scrape our simple client, which is accessible at `localhost:9091` because of the shared host network.
    - **`job_name: "pyjoules_multirate"`**: This job defines the scraping configuration for the multirate client, available at `localhost:9092`.