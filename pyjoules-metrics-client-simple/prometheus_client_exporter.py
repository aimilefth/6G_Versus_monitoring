# pyJoules_metrics/prometheus_client_exporter.py
import time
import os
import threading
from prometheus_client import start_http_server, Gauge
from power_scraper import power_scraper

# --- Prometheus Metrics Definition ---
# We use a Gauge metric type, as power is a value that can go up or down.
# We add a 'domain' label to distinguish between different energy sources (package, core, dram, etc.).
PYJOULES_ENERGY_WATTS = Gauge(
    'pyjoules_simple_energy_watts',
    'Energy consumption in Watts reported by pyJoules, on simple client',
    ['domain']
)

PYJOULES_MEASUREMENT_DURATION = Gauge(
    'pyjoules_simple_measurement_duration_seconds',
    'Duration of the pyJoules energy measurement cycle, on simple client'
)

class MetricsExporter:
    """
    A class to handle pyJoules data scraping and Prometheus metric updates.
    """
    def __init__(self, scrape_interval_seconds: float):
        self.scrape_interval = scrape_interval_seconds
        self.power_scraper = power_scraper()

    def run_metrics_loop(self):
        """
        An infinite loop that scrapes power data and updates Prometheus metrics.
        """
        print(f"Starting pyJoules data collection loop with {self.scrape_interval}s interval...")
        while True:
            try:
                # Get a single power measurement over the defined interval
                data = self.power_scraper.get_power(interval=self.scrape_interval)

                # Update the duration metric
                duration = data.pop('duration', 0)
                PYJOULES_MEASUREMENT_DURATION.set(duration)
                
                # The timestamp and tag are metadata, not metrics for prometheus in this model
                data.pop('timestamp', None)
                data.pop('tag', None)

                # Iterate over the remaining keys, which are the energy domains
                for domain, energy_value_microjoules in data.items():
                    # Convert microjoules over the interval to average watts
                    # Power (Watts) = Energy (Joules) / Time (seconds)
                    if duration > 0:
                        energy_joules = energy_value_microjoules / 1_000_000
                        power_watts = energy_joules / duration
                        # Set the gauge for the specific domain
                        PYJOULES_ENERGY_WATTS.labels(domain=domain).set(power_watts)

            except Exception as e:
                print(f"An error occurred in the metrics loop: {e}")
                # Wait a bit before retrying to avoid spamming errors
                time.sleep(5)

def main():
    """
    Main function to start the Prometheus client and the data collection loop.
    """
    # Get configuration from environment variables
    exporter_port = int(os.getenv("EXPORTER_PORT", 9091))
    scrape_interval = float(os.getenv("SCRAPE_INTERVAL_SECONDS", 0.1))

    print(f"Starting Prometheus exporter on port {exporter_port}")
    start_http_server(exporter_port)

    # Create and start the metrics collection thread
    exporter = MetricsExporter(scrape_interval_seconds=scrape_interval)
    metrics_thread = threading.Thread(target=exporter.run_metrics_loop, daemon=True)
    metrics_thread.start()

    print("Exporter is running. Metrics available at /metrics.")
    # Keep the main thread alive
    while True:
        time.sleep(1)

if __name__ == '__main__':
    main()