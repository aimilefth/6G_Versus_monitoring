import requests
import csv
import json
from datetime import datetime

# ================= Configuration =================
# Point this to your Prometheus host port
PROMETHEUS_URL = "http://localhost:9090"

# Time window for the data (e.g., '1h', '30m', '1d')
TIME_WINDOW = "2m"

# The PromQL selector. We want all timeseries coming from our source.
# This will match the 9 timeseries from the Xavier-NX (3 metrics * 3 components)
# QUERY = f'{{source=~"xavier-nx.*"}}[{TIME_WINDOW}]'

# This will get only the VDD_IN and power_watt values
QUERY = f'xavier_nx_power_watts{{component="VDD_IN", source=~"xavier-nx.*"}}[{TIME_WINDOW}]'

# Output CSV configuration
OUTPUT_CSV = f"prometheus_xavier_nx_data_{TIME_WINDOW}.csv"
# =================================================

def fetch_data():
    print(f"Querying Prometheus at {PROMETHEUS_URL}")
    print(f"Query: {QUERY}")
    
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": QUERY}
    )
    
    if response.status_code != 200:
        print(f"Error querying Prometheus! HTTP {response.status_code}")
        print(response.text)
        return
    
    data = response.json()
    if data["status"] != "success":
        print("Prometheus query failed!")
        return
        
    results = data["data"]["result"]
    total_samples = 0
    
    print(f"Found {len(results)} distinct time series (expected ~9 for a single xavier-nx).")

    with open(OUTPUT_CSV, mode="w", newline="") as f:
        writer = csv.writer(f)
        # Header matches the client-side format + human-readable timestamp
        writer.writerow(["timestamp_ms", "timestamp_iso", "metric", "component", "source", "labels", "value"])
        
        for series in results:
            metric_labels = series["metric"]
            # Extract standard labels we care about
            metric_name = metric_labels.get("__name__", "unknown")
            component = metric_labels.get("component", "unknown")
            source = metric_labels.get("source", "unknown")
            
            # Keep the full labels JSON just in case
            labels_json = json.dumps(metric_labels, sort_keys=True)
            
            # 'values' contains tuples:[unix_timestamp_seconds, "string_value"]
            values = series.get("values",[])
            total_samples += len(values)
            
            for val in values:
                ts_sec = float(val[0])
                ts_ms = int(ts_sec * 1000)
                # Make it human readable for verification
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
                
    print(f"\nSuccessfully wrote {total_samples} raw data points to '{OUTPUT_CSV}'.")


if __name__ == "__main__":
    fetch_data()