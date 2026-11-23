"""Process snapshots and safe process termination."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import psutil

__all__ = [
    "ProcessInfo",
    "ServiceInfo",
    "kill_process",
    "process_snapshot",
    "service_action",
    "services",
]

_PREVIOUS: dict[int, tuple[float, float, float]] = {}
_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    user: str
    cpu: float
    memory: float
    rss: int
    status: str
    command: str


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    unit: str
    load: str
    active: str
    sub: str
    description: str


def process_snapshot(limit: int = 120) -> list[ProcessInfo]:
    """Return processes sorted by CPU usage.

    CPU percentages are calculated from the delta of process CPU time between
    calls, so the first call after startup reports zero for most processes.
    """
    now = time.monotonic()
    results: list[ProcessInfo] = []
    with _LOCK:
        alive: set[int] = set()
        for process in psutil.process_iter(
            ["pid", "name", "username", "memory_percent", "status", "cmdline", "create_time"]
        ):
            try:
                info = process.info
                pid = int(info["pid"])
                alive.add(pid)
                times = process.cpu_times()
                cpu_time = float(times.user + times.system)
                create = float(info.get("create_time") or 0.0)
                previous = _PREVIOUS.get(pid)
                cpu = 0.0
                if previous and previous[0] == create:
                    elapsed = now - previous[2]
                    if elapsed > 0.05:
                        cpu = max(0.0, (cpu_time - previous[1]) / elapsed * 100.0)
                _PREVIOUS[pid] = (create, cpu_time, now)
                command = " ".join(info.get("cmdline") or [])[:220]
                results.append(
                    ProcessInfo(
                        pid=pid,
                        name=str(info.get("name") or "?"),
                        user=str(info.get("username") or "?"),
                        cpu=min(999.9, cpu),
                        memory=float(info.get("memory_percent") or 0.0),
                        rss=int(getattr(process.memory_info(), "rss", 0)),
                        status=str(info.get("status") or "?"),
                        command=command,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except (OSError, ValueError):
                continue
        for pid in list(_PREVIOUS):
            if pid not in alive:
                _PREVIOUS.pop(pid, None)

    results.sort(key=lambda item: (item.cpu, item.memory), reverse=True)
    return results[:limit]


def kill_process(pid: int, *, force: bool = False) -> tuple[bool, str]:
    if pid <= 1:
        return False, "Refusing to signal PID 1 or an invalid PID."
    if pid == os.getpid():
        return False, "Refusing to kill Control Panel itself."
    try:
        process = psutil.Process(pid)
        name = process.name()
        if force:
            process.kill()
            process.wait(timeout=3)
            return True, f"{name} ({pid}) killed."
        process.terminate()
        try:
            process.wait(timeout=3)
            return True, f"{name} ({pid}) terminated."
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            return True, f"{name} ({pid}) did not stop, so it was killed."
    except psutil.NoSuchProcess:
        return False, f"Process {pid} no longer exists."
    except psutil.AccessDenied:
        return False, f"Permission denied while stopping PID {pid}."
    except (OSError, ValueError) as exc:
        return False, str(exc)


def services(user: bool = False) -> list[ServiceInfo]:
    from .commands import run

    args = ["systemctl"]
    if user:
        args.append("--user")
    args += [
        "list-units",
        "--type=service",
        "--all",
        "--no-pager",
        "--plain",
        "--no-legend",
    ]
    result = run(args, timeout=10)
    if not result.ok:
        return []
    entries: list[ServiceInfo] = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4 or not parts[0].endswith(".service"):
            continue
        entries.append(
            ServiceInfo(
                unit=parts[0],
                load=parts[1],
                active=parts[2],
                sub=parts[3],
                description=parts[4].strip() if len(parts) > 4 else "",
            )
        )
    return entries


def service_action(unit: str, verb: str, *, user: bool = False):
    from .commands import run
    from .privileged import run_privileged

    if verb not in {"start", "stop", "restart", "enable", "disable"}:
        from .commands import CommandResult

        return CommandResult((), 2, error=f"Unsupported action: {verb}")
    if not unit or any(char in unit for char in " \t\n'\"\\"):
        from .commands import CommandResult

        return CommandResult((), 2, error="Invalid unit name")
    args = ["systemctl"]
    if user:
        args.append("--user")
    args += [verb, unit]
    if user:
        return run(args, timeout=20)
    return run_privileged(args, timeout=45)
