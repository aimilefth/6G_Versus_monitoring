import os
import time
import datetime
import logging
import queue
from dataclasses import dataclass
from typing import Any, Callable

import os
import re
from pathlib import Path

log = logging.getLogger("agx-orin-jtop")


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

HOST_PROC = Path(os.getenv("HOST_PROC", "/proc"))
HOST_SYS = Path(os.getenv("HOST_SYS", "/sys"))

def get_value_from_read(path):
    try:
        with open(path, 'r') as device_file:
            return device_file.read()
    except Exception as e:
        log.warning("Error in get_value_from_read path=%s: %s", path, e)
        return None


class Ina3221PowerScraper:
    """
    INA3221 scraper using the known-correct AGX Orin rail mapping.

    Important merge rule:
    - this scraper returns only measured values
    - it does NOT create a timestamp
    - the shared scrape-loop timestamp is added by get_power()

    Returned shape is compatible with the existing template collectors:
      {
        "VDD_GPU_SOC": {"Voltage": ..., "Current": ..., "Power": ...},
        ...
        "total": {"Power": ...}
      }

    Because "total" only has Power, it will only be emitted by collect_ina_power().
    """

    def __init__(self) -> None:
        self.name = [
            "VDD_GPU_SOC",
            "VDD_CPU_CV",
            "VIN_SYS_5V0",
            "VDDQ_VDD2_1V8AO",
        ]

        self.address = [0, 0, 0, 1]
        self.channel = [1, 2, 3, 2]

        self.description = [
            "Total power consumed by GPU and SOC core which supplies to memory subsystem and various engines like nvdec, nvenc, vi, vic, isp etc.",
            "Total power consumed by CPU and CV cores i.e. DLA and PVA.",
            "Power consumed by system 5V rail which supplies to various IOs e.g. HDMI, USB, UPHY, UFS, SDMMC, EMMC, DDR etc. VDDQ_VDD2_1V8AO power is also included in VIN_SYS_5V0 power.",
            "Power consumed by DDR core, DDR IO and 1V8AO Always ON power rail.",
        ]

    def get_power(self):
        power = {}
        total_power = 0.0

        for address, channel, name in zip(self.address, self.channel, self.name):
            # Values from files are milli.
            #
            # Known-correct AGX Orin path shape:
            # /sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/...
            # /sys/bus/i2c/drivers/ina3221/1-0041/hwmon/hwmon2/...
            base = (
                HOST_SYS
                / f"bus/i2c/drivers/ina3221/1-004{address}/hwmon/hwmon{address + 1}"
            )

            v_raw = get_value_from_read(base / f"in{channel}_input")
            i_raw = get_value_from_read(base / f"curr{channel}_input")

            if v_raw is None or i_raw is None:
                continue

            try:
                v = int(v_raw) / 1000.0
                i = int(i_raw) / 1000.0
            except ValueError:
                log.warning(
                    "INA3221 bad values component=%s voltage=%r current=%r",
                    name,
                    v_raw,
                    i_raw,
                )
                continue

            p = v * i

            power[name] = {
                "Voltage": v,
                "Current": i,
                "Power": p,
            }

            if name != "VDDQ_VDD2_1V8AO":
                # VDDQ_VDD2_1V8AO is already included in VIN_SYS_5V0.
                total_power += p

        # Compatible with the existing section-based collectors:
        # collect_ina_power() will emit this as component="total".
        # collect_ina_voltage/current() will ignore it because those fields do not exist.
        if power:
            power["total"] = {
                "Power": total_power,
            }

        return power

CPU_LINE_RE = re.compile(r"^cpu(\d+)\s+(.*)$")
KNOWN_GPU_NAMES = {"gv11b", "gp10b", "ga10b", "gb10b", "gpu"}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except Exception:
        return None


def _read_int(path: Path) -> int | None:
    txt = _read_text(path)
    if txt is None:
        return None
    try:
        return int(txt)
    except ValueError:
        return None


def _read_float(path: Path) -> float | None:
    txt = _read_text(path)
    if txt is None:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _parse_meminfo(proc_root: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    try:
        with (proc_root / "meminfo").open("r") as f:
            for line in f:
                key, rest = line.split(":", 1)
                value = rest.strip().split()[0]
                out[key] = float(value)  # KiB
    except Exception:
        return {}
    return out


def _parse_proc_stat(proc_root: Path) -> dict[int, list[float]]:
    out: dict[int, list[float]] = {}
    try:
        with (proc_root / "stat").open("r") as f:
            for line in f:
                m = CPU_LINE_RE.match(line)
                if not m:
                    continue

                cpu_id = int(m.group(1))

                # Match jtop's behavior: first 7 proc/stat fields.
                fields = [float(x) for x in m.group(2).split()[:7]]
                fields.append(sum(fields))
                out[cpu_id] = fields
    except Exception:
        return {}
    return out


class DirectJetson:
    """
    Small jtop-compatible read-only backend.

    Exposes:
      - .cpu
      - .memory
      - .gpu
      - .temperature
    """

    def __init__(self, proc_root: Path = HOST_PROC, sys_root: Path = HOST_SYS):
        self.proc_root = proc_root
        self.sys_root = sys_root
        self._last_cpu: dict[int, list[float]] = {}
        self._gpu_devices = self._discover_gpus()

        self.cpu: dict = {"cpu": []}
        self.memory: dict = {}
        self.gpu: dict = {}
        self.temperature: dict = {}
        self._ina3221_scraper = Ina3221PowerScraper()
        self._refresh_seq = 0
        self._ina3221_cache_seq = -1
        self._ina3221_cache: dict = {}

    def refresh(self) -> None:
        self._refresh_seq += 1

        self.cpu = self._read_cpu()
        self.memory = self._read_memory()
        self.gpu = self._read_gpu()
        self.temperature = self._read_temperature()

    def _read_cpu(self) -> dict:
        samples = _parse_proc_stat(self.proc_root)
        cpu_root = self.sys_root / "devices/system/cpu"

        cpus: list[dict] = []
        for cpu_id in sorted(samples):
            cpu_dir = cpu_root / f"cpu{cpu_id}"
            item: dict = {}

            online_txt = _read_text(cpu_dir / "online")
            item["online"] = online_txt != "0"

            freq_dir = cpu_dir / "cpufreq"
            if item["online"] and freq_dir.is_dir():
                freq: dict = {}

                cur = (
                    _read_int(freq_dir / "scaling_cur_freq")
                    or _read_int(freq_dir / "cpuinfo_cur_freq")
                )
                mn = (
                    _read_int(freq_dir / "scaling_min_freq")
                    or _read_int(freq_dir / "cpuinfo_min_freq")
                )
                mx = (
                    _read_int(freq_dir / "scaling_max_freq")
                    or _read_int(freq_dir / "cpuinfo_max_freq")
                )

                if cur is not None:
                    freq["cur"] = cur
                if mn is not None:
                    freq["min"] = mn
                if mx is not None:
                    freq["max"] = mx

                if freq:
                    item["freq"] = freq

            now = samples[cpu_id]
            last = self._last_cpu.get(cpu_id)

            if last is not None:
                delta = [n - l for n, l in zip(now, last)]
                total = delta[-1]
                idle = 100.0 * delta[3] / total if total > 0 else 100.0
                item["idle"] = max(0.0, min(100.0, idle))
            else:
                # First sample cannot estimate a delta yet.
                item["idle"] = 100.0

            self._last_cpu[cpu_id] = now
            cpus.append(item)

        return {"cpu": cpus}

    def _read_memory(self) -> dict:
        mem = _parse_meminfo(self.proc_root)
        total = mem.get("MemTotal")
        if not total:
            return {}

        free = mem.get("MemFree", 0.0)
        available = mem.get("MemAvailable", 0.0)
        buffers = mem.get("Buffers", 0.0)
        cached = mem.get("Cached", 0.0) + mem.get("SReclaimable", 0.0)

        # Used excluding buffers/cache.
        used = max(0.0, total - free - buffers - cached)

        swap_total = mem.get("SwapTotal", 0.0)
        swap_free = mem.get("SwapFree", 0.0)
        swap_used = max(0.0, swap_total - swap_free)

        return {
            "RAM": {
                "tot": total,
                "used": used,
                "free": free,
                "available": available,
                "buffers": buffers,
                "cached": cached,
            },
            "SWAP": {
                "tot": swap_total,
                "used": swap_used,
                "free": swap_free,
            },
            "MEMINFO": mem,
        }

    def _resolve_sys_path(self, path: Path) -> Path:
        real = Path(os.path.realpath(path))
        if self.sys_root != Path("/sys") and str(real).startswith("/sys/"):
            return self.sys_root / real.relative_to("/sys")
        return real

    def _discover_gpus(self) -> dict[str, dict[str, Path]]:
        """
        Discover Jetson GPU sysfs paths.

        Xavier NX commonly exposes:
        /sys/devices/platform/17000000.gv11b/load

        The devfreq directory may appear either below the GPU device or through
        /sys/class/devfreq.
        """
        out: dict[str, dict[str, Path]] = {}

        # First: explicit Xavier NX / AGX Xavier path.
        for rel in (
            "devices/platform/17000000.gv11b",
            "devices/17000000.gv11b",
        ):
            dev_path = self.sys_root / rel
            load_path = dev_path / "load"

            if load_path.exists():
                frq_path = dev_path / "devfreq" / "17000000.gv11b"

                out["gv11b"] = {
                    "path": dev_path,
                    "load_path": load_path,
                    "frq_path": frq_path,
                }

                log.info(
                    "GPU discovered name=gv11b load_path=%s frq_path=%s",
                    load_path,
                    frq_path,
                )
                return out

        # Second: generic devfreq fallback.
        devfreq_root = self.sys_root / "class/devfreq"
        if devfreq_root.is_dir():
            for entry in devfreq_root.iterdir():
                if not (entry.is_dir() or entry.is_symlink()):
                    continue

                entry_name = entry.name.lower()
                of_node_name = (_read_text(entry / "device/of_node/name") or "").lower()

                if (
                    "gv11b" not in entry_name
                    and "gp10b" not in entry_name
                    and "gpu" not in entry_name
                    and "gv11b" not in of_node_name
                    and "gp10b" not in of_node_name
                    and "gpu" not in of_node_name
                ):
                    continue

                dev_path = self._resolve_sys_path(entry / "device")
                load_path = dev_path / "load"

                if not load_path.exists():
                    log.debug(
                        "GPU candidate skipped: entry=%s dev_path=%s load_path_missing=%s",
                        entry,
                        dev_path,
                        load_path,
                    )
                    continue

                name = of_node_name or entry.name

                out[_sanitize_component(name)] = {
                    "path": dev_path,
                    "load_path": load_path,
                    "frq_path": self._resolve_sys_path(entry),
                }

                log.info(
                    "GPU discovered name=%s load_path=%s frq_path=%s",
                    name,
                    load_path,
                    self._resolve_sys_path(entry),
                )

        if not out:
            log.warning(
                "No Jetson GPU sysfs node discovered. Tried explicit gv11b paths and %s",
                devfreq_root,
            )

        return out


    def _read_gpu(self) -> dict:
        out: dict = {}

        for name, paths in self._gpu_devices.items():
            load_path = paths["load_path"]
            frq_path = paths["frq_path"]

            status: dict = {}
            freq: dict = {}

            raw_load = _read_float(load_path)
            if raw_load is not None:
                # Xavier NX gv11b load is tenths of a percent.
                status["load"] = max(0.0, min(100.0, raw_load / 10.0))
            else:
                log.debug("GPU load unreadable: %s", load_path)

            cur = _read_int(frq_path / "cur_freq")
            mn = _read_int(frq_path / "min_freq")
            mx = _read_int(frq_path / "max_freq")

            if cur is not None:
                freq["cur"] = cur // 1000
            if mn is not None:
                freq["min"] = mn // 1000
            if mx is not None:
                freq["max"] = mx // 1000

            if status or freq:
                out[name] = {
                    "type": "integrated",
                    "status": status,
                    "freq": freq,
                }

        return out

    def _read_temperature(self) -> dict:
        out: dict = {}
        thermal_root = self.sys_root / "class/thermal"

        if not thermal_root.is_dir():
            return out

        for zone in thermal_root.glob("thermal_zone*"):
            name = _read_text(zone / "type") or zone.name
            raw = _read_float(zone / "temp")
            if raw is None:
                continue

            # Linux thermal zones usually expose millidegrees Celsius.
            temp_c = raw / 1000.0 if abs(raw) > 1000 else raw
            out[name] = {"temp": temp_c}

        return out
    
    def read_ina3221(self) -> dict:
        """
        Read INA3221 once per refresh cycle.

        This is important because power, voltage, and current are three different
        collectors, but they should use the same INA3221 sample inside one scrape.
        """
        if self._ina3221_cache_seq == self._refresh_seq:
            return self._ina3221_cache

        try:
            self._ina3221_cache = self._ina3221_scraper.get_power()
        except Exception as e:
            log.warning("INA3221 scrape failed: %s", e)
            self._ina3221_cache = {}

        self._ina3221_cache_seq = self._refresh_seq
        return self._ina3221_cache


# ─────────────────────────────
# Metric configuration
# ─────────────────────────────

SERVICE_LABEL = os.getenv("SERVICE_LABEL", "agx-orin-jtop")

METRIC_CPU_UTIL = os.getenv("METRIC_CPU_UTIL", "agx_orin_cpu_util_percent")
METRIC_CPU_FREQ = os.getenv("METRIC_CPU_FREQ", "agx_orin_cpu_freq_mhz")
METRIC_MEMORY_UTIL = os.getenv("METRIC_MEMORY_UTIL", "agx_orin_memory_util_percent")
METRIC_GPU_UTIL = os.getenv("METRIC_GPU_UTIL", "agx_orin_gpu_util_percent")
METRIC_THERMAL = os.getenv("METRIC_THERMAL", "agx_orin_thermal_celsius")
METRIC_MEMORY_DETAILS = os.getenv("METRIC_MEMORY_DETAILS","agx_orin_memory_details_mb")
METRIC_POWER_W = os.getenv("METRIC_POWER_W", "agx_orin_power_watts")
METRIC_VOLTAGE_V = os.getenv("METRIC_VOLTAGE_V", "agx_orin_voltage_volts")
METRIC_CURRENT_A = os.getenv("METRIC_CURRENT_A", "agx_orin_current_amps")

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
    collect_fn: Callable[[Any], dict[str, float]]
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

    def collect_if_due(self, jetson: Any, now: float) -> dict[str, float] | None:
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

def collect_cpu_util(jetson) -> dict[str, float]:
    out: dict[str, float] = {}

    cpu_block = getattr(jetson, "cpu", {}) or {}
    for idx, cpu in enumerate(cpu_block.get("cpu", [])):
        if not cpu.get("online", True):
            continue

        idle = _safe_float(cpu.get("idle"))
        if idle is not None:
            out[f"cpu{idx}"] = max(0.0, min(100.0, 100.0 - idle))

    return out


def collect_cpu_freq(jetson) -> dict[str, float]:
    out: dict[str, float] = {}

    cpu_block = getattr(jetson, "cpu", {}) or {}
    for idx, cpu in enumerate(cpu_block.get("cpu", [])):
        if not cpu.get("online", True):
            continue

        cur = _safe_float((cpu.get("freq") or {}).get("cur"))
        if cur is not None:
            # cpufreq is mhz
            out[f"cpu{idx}"] = cur / 1000.0

    return out


def collect_memory_util(jetson) -> dict[str, float]:
    out: dict[str, float] = {}

    ram = (getattr(jetson, "memory", {}) or {}).get("RAM", {})
    used = _safe_float(ram.get("used"))
    total = _safe_float(ram.get("tot"))

    if used is not None and total and total > 0:
        out["RAM"] = max(0.0, min(100.0, 100.0 * used / total))

    return out

def collect_memory_details(jetson) -> dict[str, float]:
    """
    Export detailed memory values in MiB.

    /proc/meminfo exposes KiB.
    KiB / 1024 = MiB.
    """
    out: dict[str, float] = {}

    memory = getattr(jetson, "memory", {}) or {}

    ram = memory.get("RAM", {})
    swap = memory.get("SWAP", {})
    raw = memory.get("MEMINFO", {})

    def put(name: str, value) -> None:
        value = _safe_float(value)
        if value is not None:
            out[name] = value / 1024.0

    # RAM summary
    put("ram_total", ram.get("tot"))
    put("ram_used", ram.get("used"))
    put("ram_free", ram.get("free"))
    put("ram_available", ram.get("available"))
    put("ram_buffers", ram.get("buffers"))
    put("ram_cached", ram.get("cached"))

    # Swap summary
    put("swap_total", swap.get("tot"))
    put("swap_used", swap.get("used"))
    put("swap_free", swap.get("free"))
    put("swap_cached", raw.get("SwapCached"))

    # Useful kernel buckets
    put("shared", raw.get("Shmem"))
    put("slab", raw.get("Slab"))
    put("slab_reclaimable", raw.get("SReclaimable"))
    put("slab_unreclaimable", raw.get("SUnreclaim"))
    put("page_tables", raw.get("PageTables"))
    put("kernel_stack", raw.get("KernelStack"))
    put("vmalloc_used", raw.get("VmallocUsed"))

    return out


def collect_gpu_util(jetson) -> dict[str, float]:
    out: dict[str, float] = {}

    for name, data in (getattr(jetson, "gpu", {}) or {}).items():
        load = _safe_float((data.get("status") or {}).get("load"))
        if load is not None:
            out[_sanitize_component(name)] = max(0.0, min(100.0, load))

    return out


def collect_thermal(jetson) -> dict[str, float]:
    out: dict[str, float] = {}

    for name, data in (getattr(jetson, "temperature", {}) or {}).items():
        component = _sanitize_component(name)

        if component.lower() == "pmic_die":
            continue

        temp = data.get("temp") if isinstance(data, dict) else data
        temp = _safe_float(temp)
        if temp is not None:
            out[component] = temp

    return out

def _collect_ina3221_field(jetson, field_name: str) -> dict[str, float]:
    out: dict[str, float] = {}

    ina = jetson.read_ina3221()
    if not isinstance(ina, dict):
        return out

    for component, payload in ina.items():
        if not isinstance(payload, dict):
            continue

        value = _safe_float(payload.get(field_name))
        if value is not None:
            out[str(component)] = value

    return out


def collect_ina_power(jetson) -> dict[str, float]:
    return _collect_ina3221_field(jetson, "Power")


def collect_ina_voltage(jetson) -> dict[str, float]:
    return _collect_ina3221_field(jetson, "Voltage")


def collect_ina_current(jetson) -> dict[str, float]:
    return _collect_ina3221_field(jetson, "Current")


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
    CollectorSpec(
        name="memory_details",
        enabled_env="ENABLE_MEMORY_DETAILS",
        interval_env="MEMORY_DETAILS_INTERVAL_S",
        collect_fn=collect_memory_details,
    ),
    CollectorSpec(
        name="ina_power",
        enabled_env="ENABLE_POWER",
        interval_env="POWER_INTERVAL_S",
        collect_fn=collect_ina_power,
    ),
    CollectorSpec(
        name="ina_voltage",
        enabled_env="ENABLE_VOLTAGE",
        interval_env="VOLTAGE_INTERVAL_S",
        collect_fn=collect_ina_voltage,
    ),
    CollectorSpec(
        name="ina_current",
        enabled_env="ENABLE_CURRENT",
        interval_env="CURRENT_INTERVAL_S",
        collect_fn=collect_ina_current,
    ),
]


class power_scraper:
    """
    jtop-backed scraper.

    This keeps the same shape/style as your existing agx-orin monitor:
      get_power() returns a raw dictionary
      process_data() normalizes to Prometheus remote-write records
    """

    def get_power(self, jetson: Any) -> dict[str, Any]:
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


def get_power(raw_queue, scrape_interval_s: float, stop_event) -> None:
    jetson = DirectJetson()

    log.info(
        "direct Jetson collector started proc_root=%s sys_root=%s service=%s",
        jetson.proc_root,
        jetson.sys_root,
        SERVICE_LABEL,
    )

    batch_idx = 0

    while not stop_event.is_set():
        loop_started = time.monotonic()

        # One timestamp for the entire scrape cycle.
        timestamp = _utc_iso()

        jetson.refresh()

        raw: dict = {"timestamp": timestamp}

        for spec in COLLECTORS:
            section = spec.collect_if_due(jetson, loop_started)
            if section:
                raw[spec.name] = section

        sections = [k for k in raw.keys() if k != "timestamp"]

        if sections:
            batch_idx += 1
            log.info("direct Jetson batch #%d sections=%s", batch_idx, sections)
            raw_queue.put(raw)

        elapsed = time.monotonic() - loop_started
        sleep_s = max(0.0, scrape_interval_s - elapsed)
        if stop_event.wait(sleep_s):
            break

def process_data(input_queue: queue.Queue, output_queue: queue.Queue, stop_event):
    """
    Convert raw jtop dictionaries to normalized Prometheus remote-write records.
    """
    log.info("agx-orin-jtop process_data thread started (normalizing)")

    metric_by_section = {
        "cpu_util": METRIC_CPU_UTIL,
        "cpu_freq": METRIC_CPU_FREQ,
        "memory_util": METRIC_MEMORY_UTIL,
        "gpu_util": METRIC_GPU_UTIL,
        "thermal": METRIC_THERMAL,
        "memory_details": METRIC_MEMORY_DETAILS,
        "ina_power": METRIC_POWER_W,
        "ina_voltage": METRIC_VOLTAGE_V,
        "ina_current": METRIC_CURRENT_A,
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