"""Paired Windows thresholds and coverage, declared independently of either executable."""
import math
from statistics import median


METRICS = {
    "startup_ms": "timing",
    "visible_cpu_one_core_pct": "cpu", "hidden_cpu_one_core_pct": "cpu",
    "visible_working_set_mib": "memory", "hidden_working_set_mib": "memory",
    "idle_close_p95_ms": "timing", "idle_reopen_p95_ms": "timing",
    "scan_close_p95_ms": "timing", "scan_reopen_p95_ms": "timing",
    "visible_present_per_second": "present", "hidden_present_per_second": "present",
}
TRIALS = 3
IDLE_SECONDS = 15
SETTLE_SECONDS = 3
SWITCHES = 8


def p95(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1]


def summarize(trials):
    if len(trials) != TRIALS:
        raise ValueError("Three full native trials are required")
    result = {}
    for key in METRICS:
        values = [row["metrics"].get(key) for row in trials]
        if all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 for value in values):
            result[key] = median(values)
    return result


def budgets(reference):
    limits = {}
    for key, value in reference.items():
        kind = METRICS[key]
        if kind == "present":
            extra = 1 / IDLE_SECONDS
        elif kind == "memory":
            extra = max(4, .10 * value)
        elif kind == "cpu":
            extra = max(1, .20 * value)
        else:
            extra = max(10, .20 * value)
        limits[key] = math.ceil((value + extra) * 1000) / 1000
    return limits


def comparison(limits, candidate):
    rows = {}
    for key in METRICS:
        limit, observed = limits.get(key), candidate.get(key)
        passed = None if limit is None or observed is None else observed <= limit
        rows[key] = dict(maximum=limit, candidate=observed, passed=passed)
    return rows
