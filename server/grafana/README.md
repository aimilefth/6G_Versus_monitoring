# Grafana Service

This directory contains resources related to the Grafana service.

## Role in the Project

Grafana is the visualization layer of our monitoring stack. It is a powerful open-source platform for querying, visualizing, and understanding metrics.

In this project, Grafana's role is to:
1.  **Connect to Prometheus:** It uses Prometheus as a data source to access the stored power consumption metrics.
2.  **Visualize Data:** It allows you to build powerful and interactive dashboards to display the energy data from the different PyJoules clients over time.
3.  **Analyze and Compare:** By visualizing the metrics from all three client prototypes on the same dashboard, you can easily compare the data granularity and behavior of the different collection methods.

## Service Configuration

### `docker-compose.yml`

The Grafana service is defined in the `server/docker-compose.yml` file:
- **`image: ${GRAFANA_IMAGE}`**: Specifies the official Grafana Docker image, configured via the `server/.env` file.
- **`networks: - monitoring`**: Connects Grafana to the same bridge network as Prometheus, enabling them to communicate.
- **`user: "${UID:-1001}:${GID:-1001}"`**: This ensures that Grafana runs as the current host user, preventing permission issues. The UID and GID can be set in the `server/.env` file.
- **`volumes`**: Key configuration files are mounted from the host into the container. This enables a declarative, version-controllable setup.
    - `./grafana/grafana.ini`: Custom settings for the Grafana instance.
    - `./grafana/provisioning`: Contains YAML files that automatically configure data sources and dashboard providers on startup.
    - `./grafana/dashboards`: Contains the JSON definition for dashboards that will be loaded by the provisioner.

### Automatic Provisioning
This project uses Grafana's provisioning feature to automate setup. Instead of manually configuring Grafana through the UI, the necessary configuration is defined in files:

1.  **Data Source (`./provisioning/datasources/pyjoules.prom.yml`)**: This file tells Grafana to create a Prometheus data source named `Prometheus`, pointing to `http://prometheus:9090`. Since Grafana is on the same Docker network, it can reach Prometheus via its service name.
2.  **Dashboard (`./provisioning/dashboards/pyjoules.dash.yml` and `./dashboards/pyjoules.json`)**: The YAML file configures a dashboard provider that loads all JSON files from the `/etc/grafana/dashboards` directory inside the container. The `pyjoules.json` file is mounted into this location, making the dashboard available instantly.

When the service starts, you can navigate to [http://localhost:3000](http://localhost:3000), log in (`admin`/`6GVERSUS`), and the data source and dashboard will already be configured.