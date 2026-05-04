import os
import time
import datetime
import logging
import queue
from dataclasses import dataclass
from typing import Any, Callable

from jtop import jtop

log = logging.getLogger("xavier-nx-jtop")


# ─────────────────────────────
# Environment helpers
# ─────────────────────────────

def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("Invalid float for %s=%r; using %s", name, raw, default)
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def _iso_to_ms(iso_str: str) -> int:
    dt = datetime.datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def _sanitize_component(value: Any) -> str:
    """
    Keep label values readable and stable.
    Prometheus label values can contain almost anything, but keeping them simple
    makes Grafana legends nicer.
    """
    text = str(value).strip()
    return (
        text.replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace("-", "_")
    )


# ─────────────────────────────
# Metric configuration
# ─────────────────────────────

SERVICE_LABEL = os.getenv("SERVICE_LABEL", "xavier-nx-jtop")

METRIC_CPU_UTIL = os.getenv("METRIC_CPU_UTIL", "xavier_nx_cpu_util_percent")
METRIC_CPU_FREQ = os.getenv("METRIC_CPU_FREQ", "xavier_nx_cpu_freq_khz")
METRIC_MEMORY_UTIL = os.getenv("METRIC_MEMORY_UTIL", "xavier_nx_memory_util_percent")
METRIC_GPU_UTIL = os.getenv("METRIC_GPU_UTIL", "xavier_nx_gpu_util_percent")
METRIC_THERMAL = os.getenv("METRIC_THERMAL", "xavier_nx_thermal_celsius")

SKIP_OFFLINE_THERMAL = _env_bool("SKIP_OFFLINE_THERMAL", True)
JTOP_RECONNECT_DELAY_S = _env_float("JTOP_RECONNECT_DELAY_S", 3.0)


# ─────────────────────────────
# Modular collector registry
# ─────────────────────────────

@dataclass
class CollectorSpec:
    name: str
    enabled_env: str
    interval_env: str
    collect_fn: Callable[[jtop], dict[str, float]]
    last_run_monotonic: float = 0.0

    @property
    def enabled(self) -> bool:
        return _env_bool(self.enabled_env, True)

    @property
    def interval_s(self) -> float:
        return max(0.0, _env_float(self.interval_env, 0.0))

    def due(self, now: float) -> bool:
        interval = self.interval_s
        if interval <= 0.0:
            return True
        return (now - self.last_run_monotonic) >= interval

    def collect_if_due(self, jetson: jtop, now: float) -> dict[str, float] | None:
        if not self.enabled:
            return None
        if not self.due(now):
            return None

        t0 = time.perf_counter()
        data = self.collect_fn(jetson)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.last_run_monotonic = now

        if elapsed_ms > 100:
            log.warning("Collector %s took %.1f ms", self.name, elapsed_ms)
        else:
            log.debug("Collector %s took %.1f ms", self.name, elapsed_ms)

        return data


# ─────────────────────────────
# Individual collectors
#
# To disable a collector permanently, either:
#   1. set ENABLE_...=false in .env, or
#   2. comment it out from COLLECTORS below.
# ─────────────────────────────

def collect_cpu_util(jetson: jtop) -> dict[str, float]:
    """
    Per-CPU utilization.

    jtop CPU entries usually contain fields such as:
      user, nice, system, idle

    We export busy utilization as:
      100 - idle

    If idle is missing but a direct val/load field exists, we use that.
    """
    out: dict[str, float] = {}

    cpu_block = jetson.cpu
    cpu_list = cpu_block.get("cpu", [])

    for idx, cpu in enumerate(cpu_list):
        if not isinstance(cpu, dict):
            continue

        if cpu.get("online") is False:
            # Export offline CPUs as 0 utilization.
            out[f"cpu{idx}"] = 0.0
            continue

        idle = _safe_float(cpu.get("idle"))
        if idle is not None:
            out[f"cpu{idx}"] = max(0.0, min(100.0, 100.0 - idle))
            continue

        # Fallbacks for possible jtop/tegrastats-shaped outputs.
        for key in ("val", "load", "usage", "util"):
            val = _safe_float(cpu.get(key))
            if val is not None:
                out[f"cpu{idx}"] = max(0.0, min(100.0, val))
                break

    return out


def collect_cpu_freq(jetson: jtop) -> dict[str, float]:
    """
    Per-CPU current frequency.

    jtop CPU entries usually expose:
      cpu["freq"]["cur"]

    In jetson-stats this is typically kHz for CPU frequency.
    """
    out: dict[str, float] = {}

    cpu_block = jetson.cpu
    cpu_list = cpu_block.get("cpu", [])

    for idx, cpu in enumerate(cpu_list):
        if not isinstance(cpu, dict):
            continue

        if cpu.get("online") is False:
            out[f"cpu{idx}"] = 0.0
            continue

        freq = cpu.get("freq", {})
        cur = None

        if isinstance(freq, dict):
            cur = _safe_float(freq.get("cur"))

        # Fallbacks for alternate shapes.
        if cur is None:
            cur = _safe_float(cpu.get("frq"))
        if cur is None:
            cur = _safe_float(cpu.get("freq"))

        if cur is not None:
            out[f"cpu{idx}"] = cur

    return out


def collect_memory_util(jetson: jtop) -> dict[str, float]:
    """
    Memory utilization as percent.

    jtop.memory["RAM"] normally contains:
      tot, used, free, buffers, cached, shared, ...

    Values are usually in KiB. Since this metric is a ratio, the unit cancels out.
    """
    out: dict[str, float] = {}

    mem = jetson.memory
    ram = mem.get("RAM", {}) if hasattr(mem, "get") else {}

    used = _safe_float(ram.get("used"))
    total = _safe_float(ram.get("tot"))

    if used is not None and total and total > 0:
        out["RAM"] = max(0.0, min(100.0, 100.0 * used / total))

    return out

def collect_gpu_util(jetson: jtop) -> dict[str, float]:
    """
    GPU utilization as percent.

    jtop.gpu is dict-like:
      {
        "gpu": {
          "status": {"load": ...},
          "freq": {...}
        }
      }
    """
    out: dict[str, float] = {}

    gpu_block = jetson.gpu

    for gpu_name, gpu_payload in gpu_block.items():
        if not isinstance(gpu_payload, dict):
            continue

        status = gpu_payload.get("status", {})
        if not isinstance(status, dict):
            continue

        load = _safe_float(status.get("load"))
        if load is not None:
            out[_sanitize_component(gpu_name)] = max(0.0, min(100.0, load))

    return out


def collect_thermal(jetson: jtop) -> dict[str, float]:
    """
    Thermal sensors in Celsius.

    jtop.temperature is usually:
      {
        "CPU": {"temp": 45.5, "online": true, ...},
        "GPU": {"temp": 44.0, "online": true, ...}
      }
    """
    out: dict[str, float] = {}

    thermal_block = jetson.temperature

    for sensor_name, sensor_payload in thermal_block.items():
        if not isinstance(sensor_payload, dict):
            continue

        temp = _safe_float(sensor_payload.get("temp"))
        online = sensor_payload.get("online", True)

        if temp is None:
            continue

        if SKIP_OFFLINE_THERMAL and (online is False or temp <= -255.0):
            continue

        out[_sanitize_component(sensor_name)] = temp

    return out


COLLECTORS: list[CollectorSpec] = [
    CollectorSpec(
        name="cpu_util",
        enabled_env="ENABLE_CPU_UTIL",
        interval_env="CPU_UTIL_INTERVAL_S",
        collect_fn=collect_cpu_util,
    ),
    CollectorSpec(
        name="cpu_freq",
        enabled_env="ENABLE_CPU_FREQ",
        interval_env="CPU_FREQ_INTERVAL_S",
        collect_fn=collect_cpu_freq,
    ),
    CollectorSpec(
        name="memory_util",
        enabled_env="ENABLE_MEMORY_UTIL",
        interval_env="MEMORY_UTIL_INTERVAL_S",
        collect_fn=collect_memory_util,
    ),
    CollectorSpec(
        name="gpu_util",
        enabled_env="ENABLE_GPU_UTIL",
        interval_env="GPU_UTIL_INTERVAL_S",
        collect_fn=collect_gpu_util,
    ),
    CollectorSpec(
        name="thermal",
        enabled_env="ENABLE_THERMAL",
        interval_env="THERMAL_INTERVAL_S",
        collect_fn=collect_thermal,
    ),
]


class power_scraper:
    """
    jtop-backed scraper.

    This keeps the same shape/style as your existing xavier-nx monitor:
      get_power() returns a raw dictionary
      process_data() normalizes to Prometheus remote-write records
    """

    def get_power(self, jetson: jtop) -> dict[str, Any]:
        now = time.monotonic()

        raw: dict[str, Any] = {
            "timestamp": _utc_iso(),
        }

        for spec in COLLECTORS:
            try:
                section = spec.collect_if_due(jetson, now)
            except Exception as e:
                log.warning("Collector %s failed: %s", spec.name, e)
                continue

            if section:
                raw[spec.name] = section

        return raw


# ─────────────────────────────
# API expected by base image
# ─────────────────────────────
def _raise_jtop_background_error_if_any(jetson):
    """
    jtop normally exposes background-thread errors through jetson.ok().

    Since this exporter intentionally does NOT call jetson.ok() in the
    sampling loop, we check the private _error field directly so that
    connection failures do not silently turn into stale metrics forever.
    """

    error = getattr(jetson, "_error", None)

    if error:
        ex_type, ex_value, tb = error
        ex_value.__traceback__ = tb
        raise ex_value

    if not getattr(jetson, "_running", False):
        raise RuntimeError("jtop background thread is not running")


def get_power(output_queue, scrape_interval_s, stop_event):
    """
    Collect raw telemetry from jtop and push raw records into output_queue.

    IMPORTANT:
    This loop owns the sampling interval.

    It does NOT wait on jetson.ok().
    It does NOT use jtop's update interval as the exporter interval.

    Timing behavior per batch:

        batch_start = time.monotonic()
        collect one full batch
        push raw batch to queue
        elapsed = time.monotonic() - batch_start

        if elapsed < SCRAPE_INTERVAL_S:
            sleep(SCRAPE_INTERVAL_S - elapsed)
        else:
            do not sleep
            print warning
    """

    requested_interval_s = max(float(scrape_interval_s), 0.0)

    raw_queue_put_timeout_s = _env_float(
        "RAW_QUEUE_PUT_TIMEOUT_S",
        default=0.2,
    )

    log.info(
        "xavier-nx-jtop get_power thread started "
        "(requested_sample_interval=%.6fs, service_label=%s). "
        "Sampling cadence is controlled by this exporter loop, not by jetson.ok().",
        requested_interval_s,
        SERVICE_LABEL,
    )

    scraper = power_scraper()
    batch_counter = 0

    while not stop_event.is_set():
        try:
            # Do NOT pass scrape_interval_s here.
            #
            # jtop() still has its own internal service/cache refresh behavior,
            # but this exporter does not wait for it and does not use it as the
            # sampling interval.
            with jtop() as jetson:
                log.info(
                    "Connected to jtop service. "
                    "jtop reported service interval=%s, user interval=%s. "
                    "Exporter sampling interval=%.6fs.",
                    getattr(jetson, "interval", "unknown"),
                    getattr(jetson, "interval_user", "unknown"),
                    requested_interval_s,
                )

                while not stop_event.is_set():
                    batch_start_monotonic = time.monotonic()
                    batch_counter += 1

                    # Do not call jetson.ok() here.
                    #
                    # We only check whether the jtop background thread has
                    # failed. This is non-blocking.
                    _raise_jtop_background_error_if_any(jetson)

                    raw = scraper.get_power(jetson)

                    sections = [
                        key for key in raw.keys()
                        if key != "timestamp"
                    ]

                    if sections:
                        log.debug(
                            "jtop batch #%d sections=%s",
                            batch_counter,
                            sections,
                        )

                        try:
                            output_queue.put(
                                raw,
                                timeout=raw_queue_put_timeout_s,
                            )
                        except queue.Full:
                            log.warning(
                                "Raw telemetry queue is full; "
                                "dropping jtop batch #%d",
                                batch_counter,
                            )
                    else:
                        log.debug(
                            "jtop batch #%d had no enabled sections",
                            batch_counter,
                        )

                    batch_elapsed_s = time.monotonic() - batch_start_monotonic
                    sleep_s = requested_interval_s - batch_elapsed_s

                    if sleep_s > 0:
                        log.debug(
                            "jtop batch #%d took %.6fs; sleeping %.6fs "
                            "to match requested interval %.6fs",
                            batch_counter,
                            batch_elapsed_s,
                            sleep_s,
                            requested_interval_s,
                        )

                        stop_event.wait(sleep_s)

                    else:
                        log.warning(
                            "jtop batch #%d took %.6fs, which is slower than "
                            "the requested interval %.6fs. "
                            "Not sleeping before next batch.",
                            batch_counter,
                            batch_elapsed_s,
                            requested_interval_s,
                        )

        except Exception as exc:
            log.exception(
                "jtop collection loop failed; reconnecting in %.1fs: %s",
                JTOP_RECONNECT_DELAY_S,
                exc,
            )
            stop_event.wait(JTOP_RECONNECT_DELAY_S)

def process_data(input_queue: queue.Queue, output_queue: queue.Queue, stop_event):
    """
    Convert raw jtop dictionaries to normalized Prometheus remote-write records.
    """
    log.info("xavier-nx-jtop process_data thread started (normalizing)")

    metric_by_section = {
        "cpu_util": METRIC_CPU_UTIL,
        "cpu_freq": METRIC_CPU_FREQ,
        "memory_util": METRIC_MEMORY_UTIL,
        "gpu_util": METRIC_GPU_UTIL,
        "thermal": METRIC_THERMAL,
    }

    while not stop_event.is_set():
        try:
            raw = input_queue.get(timeout=1)
        except queue.Empty:
            continue

        if not isinstance(raw, dict) or "timestamp" not in raw:
            log.warning("process_data: unexpected raw record %r", raw)
            continue

        try:
            ts_ms = _iso_to_ms(str(raw["timestamp"]))
        except Exception as e:
            log.warning("process_data: bad timestamp %r (%s)", raw.get("timestamp"), e)
            continue

        normalized_batch: list[dict[str, Any]] = []

        for section_name, metric_name in metric_by_section.items():
            section_values = raw.get(section_name)
            if not isinstance(section_values, dict):
                continue

            for component, value in section_values.items():
                v = _safe_float(value)
                if v is None:
                    continue

                normalized_batch.append(
                    {
                        "metric": metric_name,
                        "labels": {
                            "component": str(component),
                            "source": SERVICE_LABEL,
                        },
                        "value": v,
                        "timestamp_ms": ts_ms,
                    }
                )

        if not normalized_batch:
            continue

        try:
            output_queue.put(normalized_batch, timeout=1)
        except queue.Full:
            log.warning("process_data: processed queue full; dropping batch")