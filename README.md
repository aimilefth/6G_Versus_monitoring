# Power Consumption Monitoring with Prometheus, Grafana, and PyJoules

This project demonstrates a complete monitoring infrastructure for capturing, storing, and visualizing power consumption metrics from x86 systems using PyJoules. It showcases three different architectural patterns for exporting metrics to a Prometheus time-series database, which can then be visualized using Grafana.

The primary goal is to compare and contrast different metric collection strategies:
1.  **Simple Pull-Based:** A standard approach where Prometheus scrapes a client endpoint at a fixed interval.
2.  **Multirate Pull-Based:** An advanced pull method where the client samples data at a high frequency internally and delivers a batch of timestamped metrics upon each Prometheus scrape.
3.  **Push-Based (Remote Write):** A model where the client actively pushes data to Prometheus, decoupling the collection rate from Prometheus's scrape configuration.

## Project Structure

```
.
├── .env
├── docker-compose.yml
├── get_code_in_txt.py
├── grafana
│   ├── README.md
│   └── docker_run.sh
├── monitoring.txt
├── prometheus
│   ├── README.md
│   ├── docker_run.sh
│   └── prometheus.yml
├── pyjoules-metrics-client-multirate
│   ├── Dockerfile
│   ├── README.md
│   ├── docker_build.sh
│   ├── docker_run.sh
│   ├── power_scraper.py
│   └── prometheus_client_exporter.py
├── pyjoules-metrics-client-remote-write
│   ├── Dockerfile
│   ├── README.md
│   ├── docker_build.sh
│   ├── docker_run.sh
│   ├── power_scraper.py
│   ├── remote.proto
│   └── remote_write_pusher.py
├── pyjoules-metrics-client-simple
│   ├── Dockerfile
│   ├── README.md
│   ├── docker_build.sh
│   ├── docker_run.sh
│   ├── power_scraper.py
│   └── prometheus_client_exporter.py
└── tree.txt
```

## How to Run the Project

This project is entirely containerized using Docker and orchestrated with Docker Compose, making it easy to set up and run.

### Prerequisites
*   Docker installed and running.
*   Docker Compose installed.

### Configuration
Before starting the stack, you can customize ports, image versions, and client behavior by editing the `.env` file located in the root of the project. This file is the central place for all configuration.

### Running the Stack
To start all services (Prometheus, Grafana, and the three metric exporters), run the following command from the root of the project directory:

```bash
docker-compose up -d
```
This command will pull the necessary Docker images and start all the containers in detached mode.

### Accessing the Services
Once the containers are running, you can access the services in your web browser:
*   **Prometheus UI:** [http://localhost:9090](http://localhost:9090)
    *   You can use the expression browser to query metrics like `pyjoules_simple_energy_watts`, `pyjoules_multirate_energy_uj`, and `pyjoules_remote_write_energy_uj`.
*   **Grafana UI:** [http://localhost:3000](http://localhost:3000)
    *   Default credentials: `admin` / `admin`. You will be prompted to change the password on first login.
    *   You will need to configure a Prometheus data source. Use `http://prometheus:9090` as the URL, since Grafana and Prometheus are on the same Docker network. You can then build dashboards to visualize the data.

To stop all services, run:
```bash
docker-compose down
```

## Implemented Scenario

The `docker-compose.yml` file orchestrates a complete monitoring scenario using a dedicated bridge network called `monitoring` for inter-service communication.

1.  **Prometheus** is started as the central time-series database. Its configuration (`prometheus.yml`) is set to scrape the `simple` and `multirate` clients every 2 seconds by using their service names (e.g., `pyjoules-metrics-client-simple:9091`). It is also configured with the `remote-write-receiver` enabled to accept data from the `remote-write` client.
2.  **Grafana** is started as the visualization platform. It connects to Prometheus over the `monitoring` network.
3.  **Three PyJoules Clients** are run simultaneously, each on the `monitoring` network and demonstrating a different method of sending data to Prometheus:
    *   `pyjoules-metrics-client-simple`: Exposes metrics on port `9091`, scraped by Prometheus.
    *   `pyjoules-metrics-client-multirate`: Exposes higher-frequency metrics on port `9092`, also scraped by Prometheus.
    *   `pyjoules-metrics-client-remote-write`: Independently collects and pushes metrics directly to Prometheus's remote write endpoint, addressing it as `http://prometheus:9090/api/v1/write`.

This setup allows for direct comparison of the data resolution, resource usage, and architectural trade-offs of each metric collection method within an isolated, containerized environment.