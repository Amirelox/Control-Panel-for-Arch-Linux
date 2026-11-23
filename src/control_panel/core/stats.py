"""Live system statistics collected on a background thread."""

from __future__ import annotations

import glob
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import psutil
from PyQt6.QtCore import QThread, pyqtSignal

__all__ = ["BatteryInfo", "Stats", "StatsWorker", "collect_stats"]


@dataclass(frozen=True, slots=True)
class BatteryInfo:
    percent: int
    status: str
    plugged: bool | None
    seconds_left: int | None


@dataclass(frozen=True, slots=True)
class Stats:
    cpu: float
    cpu_per_core: tuple[float, ...]
    load: tuple[float, float, float]
    mem_used: int
    mem_total: int
    mem_percent: float
    swap_used: int
    swap_total: int
    swap_percent: float
    disk_used: int
    disk_total: int
    disk_percent: float
    net_up: float
    net_down: float
    net_sent_total: int
    net_recv_total: int
    temps: dict[str, float]
    battery: BatteryInfo | None
    timestamp: float


def _read_first(path_glob: str) -> str:
    for path in glob.glob(path_glob):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def _battery_info() -> BatteryInfo | None:
    percents: list[int] = []
    status = ""
    for path in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        try:
            raw = (Path(path) / "capacity").read_text(encoding="utf-8").strip()
            percents.append(max(0, min(100, int(raw))))
        except (OSError, ValueError):
            continue
        try:
            candidate = (Path(path) / "status").read_text(encoding="utf-8").strip()
            if candidate and candidate != "Unknown":
                status = candidate
        except OSError:
            pass

    if percents:
        percent = round(sum(percents) / len(percents))
        ac_online = _read_first("/sys/class/power_supply/A*/online")
        plugged = ac_online == "1" if ac_online else (status.lower() in {"charging", "full"})
        seconds_left: int | None = None
        try:
            sensor = psutil.sensors_battery()
        except (AttributeError, OSError):
            sensor = None
        if sensor is not None and sensor.secsleft not in (
            psutil.POWER_TIME_UNLIMITED,
            psutil.POWER_TIME_UNKNOWN,
        ):
            seconds_left = int(sensor.secsleft)
        return BatteryInfo(percent, status or "Unknown", plugged, seconds_left)

    try:
        sensor = psutil.sensors_battery()
    except (AttributeError, OSError):
        sensor = None
    if sensor is None:
        return None
    seconds_left = None
    if sensor.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        seconds_left = int(sensor.secsleft)
    return BatteryInfo(round(sensor.percent), "Unknown", sensor.power_plugged, seconds_left)


def _temperatures() -> dict[str, float]:
    try:
        sensors = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return {}
    result: dict[str, float] = {}
    for name, readings in sensors.items():
        for reading in readings:
            if reading.current and reading.current > 0:
                key = f"{name}/{reading.label or 'core'}"
                result[key] = float(reading.current)
    return result


def collect_stats(
    *,
    cpu_percent: float = 0.0,
    cpu_per_core: tuple[float, ...] = (),
    previous_net: tuple[int, int] | None = None,
    previous_time: float | None = None,
) -> Stats:
    """Collect one sample. Missing sensors are handled gracefully."""
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    try:
        net = psutil.net_io_counters()
        sent, received = net.bytes_sent, net.bytes_recv
    except (AttributeError, OSError):
        sent = received = 0

    now = time.monotonic()
    up_rate = down_rate = 0.0
    if previous_net is not None and previous_time is not None:
        elapsed = max(0.001, now - previous_time)
        up_rate = max(0.0, (sent - previous_net[0]) / elapsed)
        down_rate = max(0.0, (received - previous_net[1]) / elapsed)

    try:
        load = tuple(float(value) for value in os.getloadavg())
    except (AttributeError, OSError):
        load = (0.0, 0.0, 0.0)

    return Stats(
        cpu=float(cpu_percent),
        cpu_per_core=tuple(float(value) for value in cpu_per_core),
        load=load,  # type: ignore[arg-type]
        mem_used=memory.used,
        mem_total=memory.total,
        mem_percent=memory.percent,
        swap_used=swap.used,
        swap_total=swap.total,
        swap_percent=swap.percent,
        disk_used=disk.used,
        disk_total=disk.total,
        disk_percent=disk.percent,
        net_up=up_rate,
        net_down=down_rate,
        net_sent_total=sent,
        net_recv_total=received,
        temps=_temperatures(),
        battery=_battery_info(),
        timestamp=time.time(),
    )


class StatsWorker(QThread):
    """Emit a :class:`Stats` sample roughly every ``interval_ms``."""

    stats_ready = pyqtSignal(object)

    def __init__(self, interval_ms: int = 1000, parent=None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()
        self._interval = max(0.25, interval_ms / 1000.0)

    def set_interval(self, interval_ms: int) -> None:
        self._interval = max(0.25, min(10.0, interval_ms / 1000.0))

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
            net = psutil.net_io_counters()
            previous_net = (net.bytes_sent, net.bytes_recv)
            previous_time = time.monotonic()
        except Exception:
            previous_net = None
            previous_time = None

        while not self._stop.wait(self._interval):
            try:
                per_core = tuple(psutil.cpu_percent(interval=None, percpu=True) or ())
                cpu = sum(per_core) / len(per_core) if per_core else 0.0
            except Exception:
                per_core = ()
                cpu = 0.0

            sample = collect_stats(
                cpu_percent=cpu,
                cpu_per_core=per_core,
                previous_net=previous_net,
                previous_time=previous_time,
            )
            try:
                net = psutil.net_io_counters()
                previous_net = (net.bytes_sent, net.bytes_recv)
                previous_time = time.monotonic()
            except Exception:
                previous_net = None
                previous_time = None

            self.stats_ready.emit(sample)
