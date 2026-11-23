"""NetworkManager, DNS and interface helpers."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass

import psutil

from .commands import CommandResult, run, which
from .fs import read_text
from .parsers import (
    NmDevice,
    WifiNetwork,
    parse_nmcli_devices,
    parse_nmcli_wifi,
    parse_resolv_conf,
)
from .privileged import run_privileged

__all__ = [
    "InterfaceInfo",
    "connect_wifi",
    "default_interface",
    "disconnect_wifi",
    "dns_status",
    "flush_dns",
    "interfaces",
    "networkmanager_active",
    "nm_devices",
    "ping",
    "scan_wifi",
    "set_dns",
    "start_networkmanager",
    "toggle_wifi",
    "wifi_radio",
]


@dataclass(frozen=True, slots=True)
class InterfaceInfo:
    name: str
    up: bool
    ipv4: str
    ipv6: str
    mac: str
    speed: int

    @property
    def state(self) -> str:
        return "UP" if self.up else "DOWN"


def interfaces() -> list[InterfaceInfo]:
    addresses = psutil.net_if_addrs()
    statistics = psutil.net_if_stats()
    result: list[InterfaceInfo] = []
    for name, entries in addresses.items():
        stats = statistics.get(name)
        ipv4 = next(
            (entry.address for entry in entries if entry.family == socket.AF_INET),
            "—",
        )
        ipv6 = next(
            (
                entry.address.split("%", 1)[0]
                for entry in entries
                if entry.family == socket.AF_INET6
            ),
            "—",
        )
        mac = next(
            (
                entry.address
                for entry in entries
                if getattr(entry.family, "name", "") == "AF_PACKET"
            ),
            "—",
        )
        result.append(
            InterfaceInfo(
                name=name,
                up=bool(stats and stats.isup),
                ipv4=ipv4,
                ipv6=ipv6,
                mac=mac,
                speed=int(stats.speed) if stats else 0,
            )
        )
    return sorted(result, key=lambda entry: (entry.name == "lo", not entry.up, entry.name))


def networkmanager_active() -> tuple[bool | None, str]:
    systemctl = which("systemctl")
    if systemctl is None:
        return None, "systemctl not available"
    result = run([systemctl, "is-active", "NetworkManager"], timeout=6)
    state = (result.stdout or result.stderr).strip()
    return state == "active", state or "inactive"


def nm_devices() -> tuple[list[NmDevice], str]:
    if which("nmcli") is None:
        return [], "nmcli is not installed"
    result = run(
        [
            "nmcli",
            "-t",
            "--escape",
            "yes",
            "-f",
            "DEVICE,TYPE,STATE,CONNECTION",
            "device",
            "status",
        ],
        timeout=8,
    )
    if not result.ok:
        return [], result.summary()
    return parse_nmcli_devices(result.stdout), ""


def wifi_device() -> tuple[NmDevice | None, str]:
    devices, error = nm_devices()
    for device in devices:
        if device.kind == "wifi":
            return device, ""
    return None, error or "No WiFi device found"


def wifi_radio() -> tuple[bool | None, str]:
    if which("nmcli") is None:
        return None, "nmcli is not installed"
    result = run(["nmcli", "radio", "wifi"], timeout=6)
    if not result.ok:
        return None, result.summary()
    state = result.stdout.strip().lower()
    return state == "enabled", state


def scan_wifi() -> tuple[list[WifiNetwork], str]:
    if which("nmcli") is None:
        return [], "nmcli is not installed"
    result = run(
        [
            "nmcli",
            "-t",
            "--escape",
            "yes",
            "-f",
            "IN-USE,SSID,BSSID,SIGNAL,SECURITY",
            "device",
            "wifi",
            "list",
            "--rescan",
            "yes",
        ],
        timeout=25,
    )
    if not result.ok:
        return [], result.summary()
    return parse_nmcli_wifi(result.stdout), ""


def connect_wifi(ssid: str, bssid: str = "", password: str = "") -> CommandResult:
    if which("nmcli") is None:
        return CommandResult(("nmcli",), 127, error="nmcli is not installed")
    args = ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
    if bssid:
        args += ["bssid", bssid]
    if password:
        args += ["password", password]
    return run(args, timeout=45)


def disconnect_wifi() -> CommandResult:
    device, error = wifi_device()
    if device is None:
        return CommandResult(("nmcli",), 1, error=error)
    return run(["nmcli", "device", "disconnect", device.device], timeout=15)


def toggle_wifi() -> tuple[bool, str]:
    enabled, state = wifi_radio()
    if enabled is None:
        return False, state
    target = "off" if enabled else "on"
    result = run(["nmcli", "radio", "wifi", target], timeout=10)
    if result.ok:
        return True, f"WiFi turned {target}."
    return False, result.summary()


def start_networkmanager() -> CommandResult:
    return run_privileged(["systemctl", "enable", "--now", "NetworkManager"], timeout=45)


def default_interface() -> str:
    result = run(["ip", "-4", "route", "show", "default"], timeout=4)
    if result.ok:
        parts = result.stdout.split()
        if "dev" in parts:
            index = parts.index("dev")
            if index + 1 < len(parts):
                return parts[index + 1]
    for name, stats in psutil.net_if_stats().items():
        if name != "lo" and stats.isup:
            return name
    return ""


def dns_status() -> tuple[list[str], str]:
    servers = parse_resolv_conf(read_text("/etc/resolv.conf"))
    details = ""
    if which("resolvectl"):
        result = run(["resolvectl", "status", "--no-pager"], timeout=6)
        if result.ok:
            lines = [
                line.strip()
                for line in result.stdout.splitlines()
                if "DNS Server" in line or "Current DNS Server" in line
            ]
            details = "\n".join(lines[:8])
    if not details:
        details = "\n".join(f"nameserver {server}" for server in servers)
    return servers, details


def set_dns(servers: list[str]) -> CommandResult:
    if not servers:
        return CommandResult((), 1, error="No DNS servers supplied")
    iface = default_interface()
    if which("resolvectl") and iface:
        result = run_privileged(["resolvectl", "dns", iface, *servers], timeout=30)
        if result.ok:
            run_privileged(["resolvectl", "flush-caches"], timeout=15)
        return result

    content = "".join(f"nameserver {server}\n" for server in servers)
    if os.geteuid() == 0:
        return run(["tee", "/etc/resolv.conf"], input_text=content, timeout=15)
    if which("pkexec"):
        return run_privileged(["tee", "/etc/resolv.conf"], input_text=content, timeout=30)
    return CommandResult((), 1, error="Setting DNS requires administrator rights.")


def flush_dns() -> CommandResult:
    if which("resolvectl"):
        return run_privileged(["resolvectl", "flush-caches"], timeout=15)
    if which("systemd-resolve"):
        return run_privileged(["systemd-resolve", "--flush-caches"], timeout=15)
    return CommandResult((), 1, error="No DNS cache tool found (systemd-resolved).")


def ping(host: str = "1.1.1.1", count: int = 3) -> CommandResult:
    return run(["ping", "-c", str(count), "-W", "3", host], timeout=count * 4 + 5)
