"""
Simple linear-regression calibration model.

Input data is one row per common timestamp. The model uses:

    calibration =
        1.6911937004
        + 1.1781966992 * agx_orin_power_watts__total
        - 0.0028431503 * gpu_util

Expected feature keys:
    agx_orin_power_watts__total
    agx_orin_gpu_util_percent__gpu
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

        total_power = _safe_float(features.get("agx_orin_power_watts__total"))
        gpu_util = _safe_float(features.get("agx_orin_gpu_util_percent__gpu"))

        if total_power is None:
            total_power = 0.0

        if gpu_util is None:
            gpu_util = 0.0

        calibration = (
            1.6911937004
            + 1.1781966992 * total_power
            - 0.0028431503 * gpu_util
        )

        outputs.append(
            {
                "timestamp_ms": row["timestamp_ms"],
                "calibrated_power": calibration,
            }
        )

    return outputs