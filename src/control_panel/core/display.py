"""Brightness, night light and Hyprland display actions."""

from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandResult, run, spawn, which
from .hyprland import hyprctl
from .privileged import run_privileged

__all__ = [
    "BrightnessState",
    "dpms",
    "get_brightness",
    "night_light_running",
    "night_light_tool",
    "set_brightness",
    "start_night_light",
    "stop_night_light",
]


@dataclass(frozen=True, slots=True)
class BrightnessState:
    percent: int
    current: int
    maximum: int
    device: str
    backend: str


def _sysfs_backlight() -> Path | None:
    candidates = sorted(glob.glob("/sys/class/backlight/*"))
    for candidate in candidates:
        path = Path(candidate)
        if (path / "max_brightness").is_file():
            return path
    return None


def get_brightness() -> BrightnessState | None:
    if which("brightnessctl"):
        current = run(["brightnessctl", "get"], timeout=4)
        maximum = run(["brightnessctl", "max"], timeout=4)
        device = run(["brightnessctl", "-m"], timeout=4)
        try:
            value = int(current.stdout.strip())
            top = int(maximum.stdout.strip())
        except ValueError:
            value = top = 0
        if top > 0:
            name = device.stdout.strip().split(",", 1)[0] if device.stdout else "device"
            return BrightnessState(
                percent=max(0, min(100, round(value / top * 100))),
                current=value,
                maximum=top,
                device=name or "device",
                backend="brightnessctl",
            )
    path = _sysfs_backlight()
    if path is None:
        return None
    try:
        current = int((path / "brightness").read_text().strip())
        maximum = int((path / "max_brightness").read_text().strip())
    except (OSError, ValueError):
        return None
    if maximum <= 0:
        return None
    return BrightnessState(
        percent=max(0, min(100, round(current / maximum * 100))),
        current=current,
        maximum=maximum,
        device=path.name,
        backend="sysfs",
    )


def set_brightness(percent: int) -> CommandResult:
    value = max(1, min(100, int(percent)))
    if which("brightnessctl"):
        result = run(["brightnessctl", "set", f"{value}%"], timeout=8)
        if result.ok:
            return result
    path = _sysfs_backlight()
    if path is None:
        return CommandResult((), 1, error="No backlight device found")
    state = get_brightness()
    if state is None:
        return CommandResult((), 1, error="Could not read the backlight device")
    raw = max(1, round(state.maximum * value / 100))
    target = path / "brightness"
    try:
        target.write_text(str(raw), encoding="ascii")
        return CommandResult(("brightness", str(raw)), 0)
    except OSError:
        return run_privileged(
            ["tee", str(target)],
            input_text=str(raw),
            timeout=20,
        )


def dpms(on: bool) -> CommandResult:
    return hyprctl("dispatch", "dpms", "on" if on else "off", timeout=6)


def night_light_tool() -> str:
    for name in ("wlsunset", "gammastep", "redshift"):
        if which(name):
            return name
    return ""


def night_light_running() -> bool:
    for name in ("wlsunset", "gammastep", "redshift"):
        if which(name):
            result = run(["pgrep", "-x", name], timeout=3)
            if result.ok and result.stdout.strip():
                return True
    return False


def start_night_light(temperature: int) -> tuple[bool, str]:
    tool = night_light_tool()
    if not tool:
        return False, "Install wlsunset, gammastep or redshift to use night light."
    stop_night_light()
    value = max(2500, min(6500, int(temperature)))
    if tool == "wlsunset":
        command = ["wlsunset", "-t", str(value), "-T", str(min(6500, value + 500))]
    elif tool == "gammastep":
        command = ["gammastep", "-O", str(value)]
    else:
        command = ["redshift", "-O", str(value)]
    process = spawn(command)
    if process is None:
        return False, f"Could not start {tool}."
    return True, f"Night light set to {value} K."


def stop_night_light() -> None:
    for name in ("wlsunset", "gammastep", "redshift"):
        if which(name):
            run(["pkill", "-x", name], timeout=4)
