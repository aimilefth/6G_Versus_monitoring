import requests
import csv
import json
import argparse
from datetime import datetime

# ================= Configuration =================
PROMETHEUS_URL = "http://localhost:9090"
# =================================================


def fetch_data(device, minutes):
    time_window = f"{minutes}m"

    # The PromQL selector. We want all timeseries coming from the selected source.
    query = f'{{source=~"{device}.*"}}[{time_window}]'

    # Output CSV configuration
    output_csv = f"prometheus_{device}_data_{time_window}.csv"

    print(f"Querying Prometheus at {PROMETHEUS_URL}")
    print(f"Device: {device}")
    print(f"Query: {query}")

    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query}
    )

    if response.status_code != 200:
        print(f"Error querying Prometheus! HTTP {response.status_code}")
        print(response.text)
        return

    data = response.json()
    if data["status"] != "success":
        print("Prometheus query failed!")
        print(data)
        return

    results = data["data"]["result"]
    total_samples = 0

    print(f"Found {len(results)} distinct time series.")

    with open(output_csv, mode="w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "timestamp_ms",
            "timestamp_iso",
            "metric",
            "component",
            "source",
            "labels",
            "value"
        ])

        for series in results:
            metric_labels = series["metric"]

            metric_name = metric_labels.get("__name__", "unknown")
            component = metric_labels.get("component", "unknown")
            source = metric_labels.get("source", "unknown")

            labels_json = json.dumps(metric_labels, sort_keys=True)

            values = series.get("values", [])
            total_samples += len(values)

            for val in values:
                ts_sec = float(val[0])
                ts_ms = int(ts_sec * 1000)
                ts_iso = datetime.utcfromtimestamp(ts_sec).isoformat() + "Z"
                metric_val = float(val[1])

                writer.writerow([
                    ts_ms,
                    ts_iso,
                    metric_name,
                    component,
                    source,
                    labels_json,
                    metric_val
                ])

    print(f"\nSuccessfully wrote {total_samples} raw data points to '{output_csv}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "device",
        choices=["xavier-nx", "agx-orin"],
        help="Device/source to fetch: xavier-nx or agx-orin"
    )
    parser.add_argument(
        "minutes",
        type=int,
        help="How many minutes of Prometheus data to fetch"
    )
    args = parser.parse_args()

    fetch_data(args.device, args.minutes)