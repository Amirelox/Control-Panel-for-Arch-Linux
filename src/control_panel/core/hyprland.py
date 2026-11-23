"""Helpers for reading and safely editing Hyprland configuration files."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandResult, run, which
from .config import hyprland_conf
from .fs import read_text, write_text_atomic
from .parsers import parse_config_errors, parse_getoption, parse_monitor_lines, parse_os_release

__all__ = [
    "ConfigLine",
    "config_files",
    "config_lines",
    "get_option",
    "hyprctl",
    "monitor_lines",
    "reload",
    "update_lines",
]


@dataclass(frozen=True, slots=True)
class ConfigLine:
    path: Path
    index: int
    text: str


def hyprctl(*args: str, timeout: float = 6.0) -> CommandResult:
    if which("hyprctl") is None:
        return CommandResult(("hyprctl", *args), 127, error="hyprctl is not installed")
    return run(["hyprctl", *args], timeout=timeout)


def _expand_source(value: str, owner: Path) -> list[Path]:
    value = value.strip().strip("\"'")
    value = os.path.expandvars(value)
    value = os.path.expanduser(value)
    if not value:
        return []
    path = Path(value)
    if not path.is_absolute():
        path = owner.parent / path
    if any(char in str(path) for char in "*?["):
        return [Path(match) for match in sorted(glob.glob(str(path)))]
    return [path]


def config_files(root: Path | None = None, *, max_depth: int = 5) -> list[Path]:
    """Return the main config plus every file it sources, recursively."""
    start = (root or hyprland_conf()).expanduser()
    result: list[Path] = []
    seen: set[Path] = set()

    def visit(path: Path, depth: int) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen or depth > max_depth or not resolved.is_file():
            return
        seen.add(resolved)
        result.append(resolved)
        for line in read_text(resolved).splitlines():
            stripped = line.strip()
            if not stripped.startswith("source") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != "source":
                continue
            for sourced in _expand_source(value, resolved):
                visit(sourced, depth + 1)

    visit(start, 0)
    return result


def config_lines(key: str, *, root: Path | None = None) -> list[ConfigLine]:
    """Find ``key=`` / ``key =`` lines across the config tree."""
    prefix = key.strip().lower()
    found: list[ConfigLine] = []
    for path in config_files(root):
        for index, line in enumerate(read_text(path).splitlines()):
            stripped = line.strip().lower()
            if stripped.startswith(f"{prefix}=") or stripped.startswith(f"{prefix} ="):
                found.append(ConfigLine(path, index, line))
    return found


def monitor_lines(*, root: Path | None = None) -> list[ConfigLine]:
    found: list[ConfigLine] = []
    for path in config_files(root):
        for index, line in parse_monitor_lines(read_text(path)):
            found.append(ConfigLine(path, index, line))
    return found


def update_lines(changes: dict[Path, dict[int, str]]) -> tuple[bool, str]:
    """Replace lines in one or more files, atomically and with backups."""
    if not changes:
        return True, ""
    for path, replacements in changes.items():
        text = read_text(path, "")
        if not text:
            return False, f"Cannot read {path}"
        lines = text.splitlines()
        for index, value in replacements.items():
            if 0 <= index < len(lines):
                lines[index] = value
        new_text = "\n".join(lines)
        if text.endswith("\n"):
            new_text += "\n"
        try:
            write_text_atomic(path, new_text, backup=True)
        except OSError as exc:
            return False, f"Could not write {path}: {exc}"
    return True, ""


def get_option(name: str, timeout: float = 5.0) -> int | float | str | bool | None:
    result = hyprctl("getoption", "-j", name, timeout=timeout)
    if not result.ok:
        return None
    return parse_getoption(result.stdout)


def reload() -> tuple[bool, list[str]]:
    result = hyprctl("reload", timeout=10.0)
    errors: list[str] = []
    check = hyprctl("configerrors", "-j", timeout=6.0)
    if check.ok:
        errors = parse_config_errors(check.stdout)
    if result.ok and not errors:
        return True, []
    return False, errors or [result.summary()]


def is_hyprland_installed() -> bool:
    return which("hyprctl") is not None


def desktop_name() -> str:
    os_release = parse_os_release(read_text("/etc/os-release"))
    return os_release.get("PRETTY_NAME", "Linux")
