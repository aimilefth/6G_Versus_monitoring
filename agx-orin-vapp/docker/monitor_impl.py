import datetime
import json
import logging
import os
import queue
import re
import time
from pathlib import Path
from typing import Any, Iterable

import requests

from model import model

log = logging.getLogger("agx-orin-vapp")

# Query-side configuration
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
INPUT_SOURCE_REGEX = os.getenv("INPUT_SOURCE_REGEX", "agx-orin-jtop-01")
INPUT_METRIC_REGEX = os.getenv("INPUT_METRIC_REGEX", "agx_orin_.*")
FETCH_LOOKBACK_S = float(os.getenv("FETCH_LOOKBACK_S", "3"))
EMIT_DELAY_S = float(os.getenv("EMIT_DELAY_S", "1"))
REQUEST_TIMEOUT_S = float(os.getenv("REQUEST_TIMEOUT_S", "5"))

# Output-side configuration
SERVICE_LABEL = os.getenv("SERVICE_LABEL", "agx-orin-vapp-01")
INPUT_SOURCE_LABEL = os.getenv("INPUT_SOURCE_LABEL", INPUT_SOURCE_REGEX)
MODEL_LABEL = os.getenv("MODEL_LABEL", "default")
METRIC_CALIBRATED_POWER = os.getenv(
    "METRIC_CALIBRATED_POWER", "agx_orin_vapp_calibrated_power_watts"
)
OUTPUT_COMPONENT = os.getenv("OUTPUT_COMPONENT", "calibrated_power")

# State is persisted so a restart does not replay old timestamps.
STATE_FILE = Path(os.getenv("STATE_FILE", "/data/agx-orin-vapp-state.json"))


# ─────────────────────────────
# Small helpers
# ─────────────────────────────

def _utc_now_ms() -> int:
    return int(time.time() * 1000)


def _ms_to_iso(ts_ms: int) -> str:
    return (
        datetime.datetime.fromtimestamp(ts_ms / 1000.0, tz=datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


DROP_EMPTY_FEATURE_TIMESTAMPS = _env_bool("DROP_EMPTY_FEATURE_TIMESTAMPS", True)


def _sanitize_feature_part(value: Any) -> str:
    text = str(value if value is not None else "unknown").replace("\x00", "").strip()
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _feature_key(metric: str, component: str) -> str:
    # Stable feature names for model.py, e.g.
    # agx_orin_power_watts__total
    # agx_orin_cpu_util_percent__cpu0
    return f"{_sanitize_feature_part(metric)}__{_sanitize_feature_part(component)}"


def _build_promql_query() -> str:
    lookback = max(FETCH_LOOKBACK_S, 0.001)

    # Use a range-vector instant query, same style as fetch_prometheus_data.py:
    #
    #   {source=~"agx-orin-jtop-01",__name__=~"agx_orin_.*"}[3s]
    #
    return (
        f'{{source=~"{INPUT_SOURCE_REGEX}",__name__=~"{INPUT_METRIC_REGEX}"}}'
        f'[{lookback:g}s]'
    )


def _load_last_sent_ts_ms() -> int:
    try:
        if not STATE_FILE.exists():
            return -1

        payload = json.loads(STATE_FILE.read_text())
        return int(payload.get("last_sent_timestamp_ms", -1))

    except Exception as e:
        log.warning("Could not read state file %s: %s", STATE_FILE, e)
        return -1


def _save_last_sent_ts_ms(ts_ms: int) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")

        tmp.write_text(
            json.dumps(
                {
                    "last_sent_timestamp_ms": int(ts_ms),
                    "last_sent_timestamp_iso": _ms_to_iso(int(ts_ms)),
                    "service": SERVICE_LABEL,
                },
                sort_keys=True,
            )
        )

        tmp.replace(STATE_FILE)

    except Exception as e:
        log.warning("Could not write state file %s: %s", STATE_FILE, e)


# ─────────────────────────────
# Prometheus fetch + timestamp alignment
# ─────────────────────────────

def _fetch_prometheus_window(session: requests.Session) -> dict[str, Any]:
    query = _build_promql_query()
    url = f"{PROMETHEUS_URL}/api/v1/query"

    started_ms = _utc_now_ms()

    response = session.get(
        url,
        params={"query": query},
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload!r}")

    results = payload.get("data", {}).get("result", [])

    return {
        "fetched_at_ms": started_ms,
        "query": query,
        "results": results,
    }


def _align_to_common_timestamps(
    prom_results: Iterable[dict[str, Any]],
    *,
    last_sent_ts_ms: int,
    cutoff_ts_ms: int,
) -> list[dict[str, Any]]:
    """
    Convert Prometheus range-vector output into one feature row per timestamp.

    Input shape from Prometheus:

      [
        {
          "metric": {
            "__name__": "...",
            "component": "...",
            "source": "..."
          },
          "values": [
            [1777969625.405, "729.6"],
            ...
          ]
        },
        ...
      ]

    Output shape passed to model(data):

      [
        {
          "timestamp_ms": 1777969625405,
          "timestamp_iso": "2026-05-05T08:27:05.405000Z",
          "features": {
            "agx_orin_cpu_freq_mhz__cpu0": 729.6,
            ...
          },
          "labels": {
            "input_source": "agx-orin-jtop-01"
          }
        },
        ...
      ]
    """
    by_ts: dict[int, dict[str, Any]] = {}

    for series in prom_results:
        labels = series.get("metric", {}) or {}

        metric = str(labels.get("__name__", "unknown"))
        component = str(labels.get("component", "unknown"))
        source = str(labels.get("source", "unknown"))

        key = _feature_key(metric, component)

        for sample in series.get("values", []) or []:
            if len(sample) != 2:
                continue

            try:
                ts_ms = int(round(float(sample[0]) * 1000.0))
                value = float(sample[1])
            except (TypeError, ValueError):
                continue

            # Overlap query window intentionally re-reads old data.
            # Only keep data newer than the last timestamp already emitted.
            if ts_ms <= last_sent_ts_ms:
                continue

            # Avoid emitting the newest samples immediately. This gives Prometheus
            # time to receive all series for the same timestamp before we pivot it.
            if ts_ms > cutoff_ts_ms:
                continue

            row = by_ts.setdefault(
                ts_ms,
                {
                    "timestamp_ms": ts_ms,
                    "timestamp_iso": _ms_to_iso(ts_ms),
                    "features": {},
                    "labels": {
                        "input_source": source,
                    },
                },
            )

            # If the selector accidentally matches multiple input sources,
            # keep the last value but make the collision visible in logs.
            # For multi-source inference, change _feature_key() to include source too.
            if key in row["features"]:
                log.debug(
                    "Duplicate feature for timestamp=%s key=%s; overwriting",
                    ts_ms,
                    key,
                )

            row["features"][key] = value

    rows = [by_ts[ts] for ts in sorted(by_ts)]

    if DROP_EMPTY_FEATURE_TIMESTAMPS:
        rows = [r for r in rows if r.get("features")]

    return rows


# ─────────────────────────────
# Model output normalization
# ─────────────────────────────

def _model_outputs_to_records(
    input_rows: list[dict[str, Any]],
    model_output: Any,
) -> list[dict[str, Any]]:
    """
    Accept a few practical model return formats:

      1. [{"timestamp_ms": ..., "calibrated_power": 12.3}, ...]
      2. [{"calibrated_power": 12.3}, ...]  # aligned by input order
      3. [12.3, 12.4, ...]                  # aligned by input order
      4. {timestamp_ms: 12.3, ...}

    Emits normalized records expected by base-monitoring-client.
    """
    records: list[dict[str, Any]] = []

    def add_record(row: dict[str, Any], calibrated_power: Any) -> None:
        try:
            value = float(calibrated_power)
        except (TypeError, ValueError):
            log.warning(
                "model returned invalid calibrated_power=%r for timestamp_ms=%s; skipping",
                calibrated_power,
                row.get("timestamp_ms"),
            )
            return

        records.append(
            {
                "metric": METRIC_CALIBRATED_POWER,
                "labels": {
                    "component": OUTPUT_COMPONENT,
                    "source": SERVICE_LABEL,
                    "input_source": INPUT_SOURCE_LABEL,
                    "model": MODEL_LABEL,
                },
                "value": value,
                "timestamp_ms": int(row["timestamp_ms"]),
            }
        )

    if isinstance(model_output, dict):
        by_ts = {int(row["timestamp_ms"]): row for row in input_rows}

        for raw_ts, value in model_output.items():
            try:
                ts_ms = int(raw_ts)
            except (TypeError, ValueError):
                log.warning(
                    "model returned non-integer timestamp key=%r; skipping",
                    raw_ts,
                )
                continue

            row = by_ts.get(ts_ms)

            if row is None:
                log.warning("model returned unknown timestamp_ms=%s; skipping", ts_ms)
                continue

            if isinstance(value, dict):
                value = value.get("calibrated_power")

            add_record(row, value)

        return records

    if not isinstance(model_output, (list, tuple)):
        raise TypeError(
            "model(data) must return a list/tuple or dict; "
            f"got {type(model_output).__name__}"
        )

    if len(model_output) != len(input_rows):
        raise ValueError(
            f"model(data) returned {len(model_output)} outputs for "
            f"{len(input_rows)} input rows"
        )

    for row, item in zip(input_rows, model_output):
        value = item.get("calibrated_power") if isinstance(item, dict) else item
        add_record(row, value)

    return records


# ─────────────────────────────
# API expected by base image
# ─────────────────────────────

def get_power(output_queue: queue.Queue, scrape_interval_s: float, stop_event) -> None:
    """
    Fetch a Prometheus range-vector window every scrape_interval_s.

    We intentionally fetch FETCH_LOOKBACK_S, which should be larger than
    SCRAPE_INTERVAL_S by about 1-2 seconds. process_data() filters timestamps
    already emitted using the persisted last_sent timestamp.
    """
    session = requests.Session()
    batch_idx = 0

    log.info(
        "agx-orin-vapp fetch thread started prometheus=%s interval=%ss "
        "lookback=%ss delay=%ss source_regex=%s metric_regex=%s",
        PROMETHEUS_URL,
        scrape_interval_s,
        FETCH_LOOKBACK_S,
        EMIT_DELAY_S,
        INPUT_SOURCE_REGEX,
        INPUT_METRIC_REGEX,
    )

    while not stop_event.is_set():
        loop_started = time.monotonic()

        try:
            raw = _fetch_prometheus_window(session)

            batch_idx += 1

            log.info(
                "fetched Prometheus batch #%d series=%d query=%s",
                batch_idx,
                len(raw.get("results", [])),
                raw.get("query"),
            )

            output_queue.put(raw, timeout=1)

        except queue.Full:
            log.warning("get_power: raw queue full; dropping fetched Prometheus batch")

        except Exception as e:
            log.warning("get_power: Prometheus fetch failed: %s", e)

        elapsed = time.monotonic() - loop_started
        sleep_s = max(0.0, scrape_interval_s - elapsed)

        if stop_event.wait(sleep_s):
            break


def process_data(
    input_queue: queue.Queue,
    output_queue: queue.Queue,
    stop_event,
) -> None:
    """
    Align samples by timestamp, call model(data), and emit calibrated_power.
    """
    last_sent_ts_ms = _load_last_sent_ts_ms()

    if last_sent_ts_ms >= 0:
        log.info(
            "agx-orin-vapp process_data started with persisted "
            "last_sent_timestamp_ms=%s (%s)",
            last_sent_ts_ms,
            _ms_to_iso(last_sent_ts_ms),
        )
    else:
        log.info("agx-orin-vapp process_data started with no persisted state")

    while not stop_event.is_set():
        try:
            raw = input_queue.get(timeout=1)
        except queue.Empty:
            continue

        if not isinstance(raw, dict) or "results" not in raw:
            log.warning("process_data: unexpected raw batch %r", raw)
            continue

        fetched_at_ms = int(raw.get("fetched_at_ms") or _utc_now_ms())
        cutoff_ts_ms = fetched_at_ms - int(max(0.0, EMIT_DELAY_S) * 1000)

        rows = _align_to_common_timestamps(
            raw.get("results", []),
            last_sent_ts_ms=last_sent_ts_ms,
            cutoff_ts_ms=cutoff_ts_ms,
        )

        if not rows:
            log.debug(
                "process_data: no eligible timestamps after last_sent=%s cutoff=%s",
                last_sent_ts_ms,
                cutoff_ts_ms,
            )
            continue

        try:
            predictions = model(rows)
            normalized_batch = _model_outputs_to_records(rows, predictions)

        except Exception as e:
            log.exception(
                "process_data: model failed; batch will be retried by overlap: %s",
                e,
            )
            continue

        if not normalized_batch:
            log.warning(
                "process_data: model produced no valid outputs for %d rows",
                len(rows),
            )
            continue

        try:
            output_queue.put(normalized_batch, timeout=1)

        except queue.Full:
            # Do not advance last_sent_ts_ms. The overlap query will see these
            # timestamps again and retry them later.
            log.warning(
                "process_data: processed queue full; not advancing last_sent timestamp"
            )
            continue

        max_emitted_ts_ms = max(int(rec["timestamp_ms"]) for rec in normalized_batch)
        last_sent_ts_ms = max(last_sent_ts_ms, max_emitted_ts_ms)
        _save_last_sent_ts_ms(last_sent_ts_ms)

        first_ts = min(int(rec["timestamp_ms"]) for rec in normalized_batch)

        log.info(
            "emitted calibrated_power records=%d timestamps=%d range=[%s, %s] "
            "last_sent=%s",
            len(normalized_batch),
            len({rec["timestamp_ms"] for rec in normalized_batch}),
            _ms_to_iso(first_ts),
            _ms_to_iso(max_emitted_ts_ms),
            _ms_to_iso(last_sent_ts_ms),
        )