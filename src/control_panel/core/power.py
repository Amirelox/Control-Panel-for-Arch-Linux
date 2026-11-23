"""Battery, power profiles and session actions."""

from __future__ import annotations

import os

from .commands import CommandResult, run, which
from .fs import read_text
from .privileged import run_privileged

__all__ = [
    "PROFILES",
    "available_profiles",
    "can_hibernate",
    "current_profile",
    "perform_action",
    "set_profile",
]

PROFILES = ("power-saver", "balanced", "performance")


def current_profile() -> str:
    if which("powerprofilesctl") is None:
        return ""
    result = run(["powerprofilesctl", "get"], timeout=5)
    return result.stdout.strip() if result.ok else ""


def available_profiles() -> list[str]:
    if which("powerprofilesctl") is None:
        return []
    result = run(["powerprofilesctl", "list"], timeout=6)
    if not result.ok:
        return list(PROFILES)
    found = [profile for profile in PROFILES if profile in result.stdout]
    return found or list(PROFILES)


def set_profile(profile: str) -> CommandResult:
    if profile not in PROFILES:
        return CommandResult((), 2, error=f"Unknown profile: {profile}")
    if which("powerprofilesctl") is None:
        return CommandResult((), 127, error="powerprofilesctl is not installed")
    return run(["powerprofilesctl", "set", profile], timeout=10)


def can_hibernate() -> bool:
    return "disk" in read_text("/sys/power/state").split()


def _lock() -> CommandResult:
    for command in (
        ["hyprlock"],
        ["swaylock"],
        ["loginctl", "lock-session"],
    ):
        if which(command[0]) is None and command[0] != "loginctl":
            continue
        result = run(command, timeout=10)
        if result.ok:
            return result
    return CommandResult(("lock",), 1, error="No screen locker found (hyprlock/swaylock).")


def perform_action(action: str, *, confirmation: bool = True) -> CommandResult:
    del confirmation  # confirmation is handled by the UI
    if action == "lock":
        return _lock()
    if action == "suspend":
        return run(["systemctl", "suspend"], timeout=15)
    if action == "hibernate":
        if not can_hibernate():
            return CommandResult((), 1, error="Hibernation is not enabled on this system.")
        return run(["systemctl", "hibernate"], timeout=15)
    if action == "logout":
        if which("hyprctl"):
            return run(["hyprctl", "dispatch", "exit"], timeout=10)
        session = os.environ.get("XDG_SESSION_ID", "").strip()
        if session:
            return run(["loginctl", "terminate-session", session], timeout=10)
        user = os.environ.get("USER", os.environ.get("LOGNAME", "")).strip()
        if user:
            return run(["loginctl", "terminate-user", user], timeout=10)
        return CommandResult((), 1, error="Could not determine the current session.")
    if action == "reboot":
        return run_privileged(["systemctl", "reboot"], timeout=20)
    if action == "shutdown":
        return run_privileged(["systemctl", "poweroff"], timeout=20)
    return CommandResult((), 2, error=f"Unknown power action: {action}")
