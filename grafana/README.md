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

The Grafana service is defined in the main `docker-compose.yml` file:
- **`image: ${GRAFANA_IMAGE}`**: Specifies the official Grafana Docker image, configured via the `.env` file.
- **`networks: - monitoring`**: Connects Grafana to the same bridge network as Prometheus, enabling them to communicate.
- **`user: "${UID:-1001}:${GID:-1001}"`**: This ensures that Grafana runs as the current host user, preventing permission issues. The UID and GID can be set in the `.env` file.
- **`volumes`**: A local directory, `./grafana/grafana-storage`, is mounted into the container at `/var/lib/grafana`. This is critical for **data persistence**, as it saves all your created dashboards and data sources.

### First-Time Setup
1.  Navigate to [http://localhost:3000](http://localhost:3000).
2.  Log in with the default credentials: `admin` / `admin`.
3.  Go to **Connections -> Data Sources** and add a new **Prometheus** data source.
4.  Set the **Prometheus server URL** to `http://prometheus:9090`. Since Grafana is on the same Docker network as Prometheus, it can reach it directly via its service name.
5.  Click **Save & Test**. You should see a confirmation that the data source is working.
6.  You can now create new dashboards and add panels that query the PyJoules metrics.