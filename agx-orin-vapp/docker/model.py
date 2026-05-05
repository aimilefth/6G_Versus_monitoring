"""
Replace this file with your real calibration model.

Contract used by monitor_impl.py:

    def model(data: list[dict]) -> list[dict] | list[float]

Input `data` is one row per common timestamp:

    {
        "timestamp_ms": 1777969625405,
        "timestamp_iso": "2026-05-05T08:27:05.405000Z",
        "features": {
            "agx_orin_cpu_freq_mhz__cpu0": 729.6,
            "agx_orin_cpu_util_percent__cpu0": 10.0,
            "agx_orin_power_watts__total": 7.028,
            ...
        },
        "labels": {"input_source": "agx-orin-jtop-01"}
    }

Return either:

    [{"timestamp_ms": row["timestamp_ms"], "calibrated_power": value}, ...]

or simply:

    [value0, value1, ...]

The default implementation is a safe pass-through baseline + 1.0: it uses
agx_orin_power_watts__total when present; otherwise it sums the non-total
agx_orin_power_watts__* features.
"""

from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def model(data: list[dict]) -> list[dict]:
    outputs: list[dict] = []

    for row in data:
        features = row.get("features", {}) or {}

        calibrated = _safe_float(features.get("agx_orin_power_watts__total"))

        if calibrated is None:
            # Fallback for early testing if the total rail is not present.
            power_values = [
                _safe_float(v)
                for k, v in features.items()
                if k.startswith("agx_orin_power_watts__") and not k.endswith("__total")
            ]
            calibrated = sum(v for v in power_values if v is not None)

        outputs.append(
            {
                "timestamp_ms": row["timestamp_ms"],
                "calibrated_power": calibrated+ 1.0,
            }
        )

    return outputs