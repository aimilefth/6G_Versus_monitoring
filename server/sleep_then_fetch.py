#!/usr/bin/env python3
import argparse
import subprocess
import time
from pathlib import Path


# ================= Configuration =================
EXTRA_WAIT_SECONDS = 5
FETCH_SCRIPT = Path(__file__).resolve().parent / "fetch_prometheus_data.py"
# =================================================


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "device",
        choices=["xavier-nx", "agx-orin"],
        help="Device/source to fetch: xavier-nx or agx-orin"
    )
    parser.add_argument("minutes", type=int, help="Experiment duration in minutes")
    args = parser.parse_args()

    total_sleep_seconds = args.minutes * 60 + EXTRA_WAIT_SECONDS

    print(f"Device: {args.device}")
    print(f"Sleeping for {args.minutes} minutes + {EXTRA_WAIT_SECONDS} seconds...")
    time.sleep(total_sleep_seconds)

    print(f"Fetching last {args.minutes} minutes of Prometheus data for {args.device}...")

    subprocess.run(
        ["python3", str(FETCH_SCRIPT), args.device, str(args.minutes)],
        check=True
    )

    print("Done.")


if __name__ == "__main__":
    main()