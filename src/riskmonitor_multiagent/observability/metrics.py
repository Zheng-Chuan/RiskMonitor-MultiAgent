from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


def _freeze_labels(labels: Optional[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    items: list[tuple[str, str]] = []
    for k, v in labels.items():
        if v is None:
            continue
        items.append((str(k), str(v)))
    items.sort(key=lambda x: x[0])
    return tuple(items)


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in labels]
    return "{" + ",".join(parts) + "}"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    idx = int(math.ceil(0.95 * len(vs))) - 1
    idx = max(0, min(idx, len(vs) - 1))
    return float(vs[idx])


@dataclass
class _Obs:
    samples: list[float]
    sum: float = 0.0
    count: int = 0

    def add(self, v: float, *, max_samples: int) -> None:
        self.sum += float(v)
        self.count += 1
        self.samples.append(float(v))
        if len(self.samples) > max_samples:
            self.samples = self.samples[-max_samples:]


class _Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._obs: dict[tuple[str, tuple[tuple[str, str], ...]], _Obs] = {}
        self._max_samples = 512

    def inc_counter(self, name: str, labels: Optional[dict[str, Any]] = None, value: int = 1) -> None:
        key = (name, _freeze_labels(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + int(value)

    def set_gauge(self, name: str, value: float, labels: Optional[dict[str, Any]] = None) -> None:
        key = (name, _freeze_labels(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def observe_ms(self, name: str, value_ms: float, labels: Optional[dict[str, Any]] = None) -> None:
        key = (name, _freeze_labels(labels))
        with self._lock:
            obs = self._obs.get(key)
            if obs is None:
                obs = _Obs(samples=[])
                self._obs[key] = obs
            obs.add(float(value_ms), max_samples=self._max_samples)

    def render(self) -> str:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            obs = dict(self._obs)
            start_time = float(self._start_time)

        lines: list[str] = []

        lines.append("# HELP process_start_time_seconds Process start time in unix timestamp")
        lines.append("# TYPE process_start_time_seconds gauge")
        lines.append(f"process_start_time_seconds {start_time}")
        lines.append("")

        uptime = time.time() - start_time
        lines.append("# HELP process_uptime_seconds Process uptime in seconds")
        lines.append("# TYPE process_uptime_seconds gauge")
        lines.append(f"process_uptime_seconds {uptime:.2f}")
        lines.append("")

        if counters:
            lines.append("# HELP rm_counters_total Internal counters")
            lines.append("# TYPE rm_counters_total counter")
            for (name, labels), v in sorted(counters.items(), key=lambda x: (x[0][0], x[0][1])):
                lines.append(f'{name}{_format_labels(labels)} {int(v)}')
            lines.append("")

        if gauges:
            lines.append("# HELP rm_gauges Internal gauges")
            lines.append("# TYPE rm_gauges gauge")
            for (name, labels), v in sorted(gauges.items(), key=lambda x: (x[0][0], x[0][1])):
                lines.append(f'{name}{_format_labels(labels)} {float(v):.6f}')
            lines.append("")

        if obs:
            lines.append("# HELP rm_observations_ms Internal observations in ms")
            lines.append("# TYPE rm_observations_ms gauge")
            for (name, labels), o in sorted(obs.items(), key=lambda x: (x[0][0], x[0][1])):
                avg = (o.sum / o.count) if o.count > 0 else 0.0
                p95 = _p95(o.samples)
                lines.append(f'{name}_ms_avg{_format_labels(labels)} {float(avg):.3f}')
                lines.append(f'{name}_ms_p95{_format_labels(labels)} {float(p95):.3f}')
                lines.append(f'{name}_ms_count{_format_labels(labels)} {int(o.count)}')
            lines.append("")

        return "\n".join(lines)

    def reset(self) -> None:
        with self._lock:
            self._start_time = time.time()
            self._counters.clear()
            self._gauges.clear()
            self._obs.clear()


_STORE = _Store()


def inc_counter(name: str, labels: Optional[dict[str, Any]] = None, value: int = 1) -> None:
    _STORE.inc_counter(name, labels=labels, value=value)


def set_gauge(name: str, value: float, labels: Optional[dict[str, Any]] = None) -> None:
    _STORE.set_gauge(name, value=value, labels=labels)


def observe_ms(name: str, value_ms: float, labels: Optional[dict[str, Any]] = None) -> None:
    _STORE.observe_ms(name, value_ms=value_ms, labels=labels)


def render_prometheus_metrics() -> str:
    return _STORE.render()


def reset_observability_metrics() -> None:
    _STORE.reset()
