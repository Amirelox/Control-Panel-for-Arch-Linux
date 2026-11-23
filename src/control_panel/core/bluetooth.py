"""Bluetooth controller and device helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .commands import CommandResult, run, which
from .parsers import BluetoothDevice, parse_bluetooth_info, parse_bluetooth_pairs
from .privileged import run_privileged

__all__ = [
    "Controller",
    "SocketInfo",
    "action",
    "available",
    "controller",
    "devices",
    "power",
    "scan",
    "start_service",
]

_MAC = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")


@dataclass(frozen=True, slots=True)
class Controller:
    available: bool
    powered: bool
    name: str
    address: str
    discovering: bool
    error: str = ""


@dataclass(frozen=True, slots=True)
class SocketInfo:
    paired: bool = False
    connected: bool = False
    trusted: bool = False


def available() -> bool:
    return which("bluetoothctl") is not None


def controller() -> Controller:
    if not available():
        return Controller(False, False, "", "", False, "bluetoothctl is not installed")
    result = run(["bluetoothctl", "show"], timeout=8)
    if not result.ok:
        return Controller(False, False, "", "", False, result.summary())
    info = parse_bluetooth_info(result.stdout)
    if not info:
        return Controller(False, False, "", "", False, "No Bluetooth controller found")
    address_match = re.search(r"^Controller\s+([0-9A-Fa-f:]{17})", result.stdout, re.MULTILINE)
    return Controller(
        available=True,
        powered=info.get("Powered", "").lower() == "yes",
        name=info.get("Name") or info.get("Alias") or "Bluetooth controller",
        address=address_match.group(1) if address_match else info.get("Controller", ""),
        discovering=info.get("Discovering", "").lower() == "yes",
    )


def _info(address: str) -> SocketInfo:
    result = run(["bluetoothctl", "info", address], timeout=6)
    if not result.ok:
        return SocketInfo()
    data = parse_bluetooth_info(result.stdout)
    return SocketInfo(
        paired=data.get("Paired", "").lower() == "yes",
        connected=data.get("Connected", "").lower() == "yes",
        trusted=data.get("Trusted", "").lower() == "yes",
    )


def devices() -> list[BluetoothDevice]:
    if not available():
        return []
    result = run(["bluetoothctl", "devices"], timeout=8)
    if not result.ok:
        return []
    entries = parse_bluetooth_pairs(result.stdout)
    enriched: list[BluetoothDevice] = []
    for entry in entries[:40]:
        state = _info(entry.address)
        enriched.append(
            BluetoothDevice(
                address=entry.address,
                name=entry.name,
                paired=state.paired,
                connected=state.connected,
                trusted=state.trusted,
            )
        )
    enriched.sort(key=lambda item: (not item.connected, not item.paired, item.name.lower()))
    return enriched


def scan(seconds: int = 8) -> CommandResult:
    if not available():
        return CommandResult((), 127, error="bluetoothctl is not installed")
    return run(
        ["bluetoothctl", "--timeout", str(max(3, min(30, seconds))), "scan", "on"],
        timeout=seconds + 10,
    )


def power(on: bool) -> CommandResult:
    if not available():
        return CommandResult((), 127, error="bluetoothctl is not installed")
    return run(["bluetoothctl", "power", "on" if on else "off"], timeout=8)


def start_service() -> CommandResult:
    return run_privileged(["systemctl", "start", "bluetooth"], timeout=30)


def action(address: str, verb: str) -> CommandResult:
    if not _MAC.fullmatch(address):
        return CommandResult((), 2, error="Invalid Bluetooth address")
    if verb not in {"connect", "disconnect", "pair", "remove", "trust", "untrust"}:
        return CommandResult((), 2, error=f"Unsupported Bluetooth action: {verb}")
    if not available():
        return CommandResult((), 127, error="bluetoothctl is not installed")
    return run(["bluetoothctl", "--timeout", "20", verb, address], timeout=30)
