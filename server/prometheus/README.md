# Prometheus Service

This directory contains the configuration for the Prometheus service.

## Role in the Project

Prometheus serves as the core of the monitoring stack. It is a powerful open-source monitoring and alerting toolkit that collects and stores its metrics as time-series data.

In this project, its key responsibilities are:
1.  **Data Storage:** Acting as the central database for all power consumption metrics collected by the monitoring clients.
2.  **Data Reception (Push):** Receiving data pushed from the `cpu-pyjoules` service via the remote write API.
3.  **Data Source for Grafana:** Providing the stored time-series data to Grafana for visualization and analysis.

## Service Configuration

### `docker-compose.yml`

The Prometheus service is defined in the `server/docker-compose.yml` file with the following key settings:
- **`image: ${PROMETHEUS_IMAGE}`**: Specifies the official Prometheus Docker image, configured via the `.env` file.
- **`networks: - monitoring`**: Connects Prometheus to the custom bridge network, allowing it to communicate with other services using their service names.
- **`volumes`**: The local `entrypoint.sh` script is mounted into the container at `/entrypoint.sh`.
- **`entrypoint`**: The container is configured to run the `/entrypoint.sh` script on startup. This script generates the `prometheus.yml` configuration file and then starts the Prometheus process.
- **`environment`**: Environment variables from the `.env` file are passed to the container to customize the generated configuration.

### `entrypoint.sh`

This script is the core of the service's configuration. Instead of using a static `prometheus.yml` file, this script dynamically generates one inside the container when it starts. This allows for flexible configuration using environment variables from the `server/.env` file (e.g., setting the scrape interval). After generating the config, it starts Prometheus with the `--web.enable-remote-write-receiver` flag activated, which is necessary for the push-based client.

### Generated `prometheus.yml`

The `entrypoint.sh` script produces a `prometheus.yml` file with the following structure:
- **`global.scrape_interval`**: Sets the frequency for scraping targets, customized by the `PROMETHEUS_SCRAPE_INTERVAL` variable.
- **`scrape_configs`**: This section defines the monitoring jobs.
    - **`job_name: "prometheus"`**: The job is for Prometheus to monitor itself.
