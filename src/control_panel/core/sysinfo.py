"""One-shot static system information for the overview page."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import time
from pathlib import Path

import psutil

from .commands import run
from .config import hyprland_conf, modules_dir
from .fs import read_text
from .parsers import format_duration, parse_lspci, parse_os_release
from .privileged import is_hyprland

__all__ = ["collect_system_info"]


def _cpu_model() -> str:
    for line in read_text("/proc/cpuinfo").splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor() or "Unknown"


def _gpu_model() -> str:
    result = run(["lspci"], timeout=4.0)
    if result.ok:
        gpus = parse_lspci(result.stdout)
        if gpus:
            return gpus[0]
    return "—"


def _compositor_version() -> str:
    if not is_hyprland():
        return os.environ.get("XDG_CURRENT_DESKTOP", "—") or "—"
    if shutil.which("hyprctl") is None:
        return "Hyprland (hyprctl not installed)"
    result = run(["hyprctl", "version", "-j"], timeout=4.0)
    if not result.ok:
        return "Hyprland"
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return "Hyprland"
    version = str(data.get("version", "")).strip()
    branch = str(data.get("branch", "")).strip()
    if version:
        return f"Hyprland {version}" + (f" ({branch})" if branch and branch != version else "")
    return "Hyprland"


def _session_type() -> str:
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").strip()
    return f"{session} · {desktop}" if desktop else session


def _config_note() -> str:
    paths = [hyprland_conf(), modules_dir()]
    return ", ".join(str(path) for path in paths if Path(path).exists()) or "not found"


def collect_system_info() -> dict[str, str]:
    os_release = parse_os_release(read_text("/etc/os-release"))
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    boot = psutil.boot_time()

    return {
        "Hostname": socket.gethostname(),
        "Operating system": os_release.get("PRETTY_NAME", platform.platform()),
        "Kernel": platform.release(),
        "Desktop": _session_type(),
        "Compositor": _compositor_version(),
        "Uptime": format_duration(time.time() - boot),
        "CPU": _cpu_model(),
        "Cores": f"{psutil.cpu_count(logical=False) or '?'} physical · "
        f"{psutil.cpu_count(logical=True) or '?'} logical",
        "Memory": f"{memory.total / (1024**3):.1f} GiB",
        "Swap": f"{swap.total / (1024**3):.1f} GiB" if swap.total else "none",
        "GPU": _gpu_model(),
        "Config": _config_note(),
    }
