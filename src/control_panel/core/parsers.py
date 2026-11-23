"""Pure parsing helpers.

The functions in this module never touch the system directly; they take command
output and return typed objects. That keeps the tricky parts testable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

__all__ = [
    "BluetoothDevice",
    "FsEntry",
    "HyprMonitor",
    "LoginRecord",
    "Package",
    "PortInfo",
    "SystemdUnit",
    "UpdateInfo",
    "WifiNetwork",
    "format_bytes",
    "format_duration",
    "format_rate",
    "mask_secret",
    "parse_bluetooth_info",
    "parse_bluetooth_pairs",
    "parse_config_errors",
    "parse_df",
    "parse_getoption",
    "parse_hypr_monitors",
    "parse_lspci",
    "parse_monitor_lines",
    "parse_nmcli_devices",
    "parse_nmcli_escaped",
    "parse_nmcli_wifi",
    "parse_os_release",
    "parse_pacman_search",
    "parse_pacman_updates",
    "parse_resolv_conf",
    "parse_ss_ports",
    "parse_sysfs_battery",
    "parse_systemd_units",
    "validate_package_name",
    "validate_wifi_password",
    "validate_wifi_ssid",
]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def format_bytes(value: float | int, *, suffix: str = "") -> str:
    """Format a byte count as e.g. ``1.4 GiB``."""
    number = float(max(0.0, value))
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    for unit in units:
        if number < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(number)} B{suffix}"
            return f"{number:.1f} {unit}{suffix}"
        number /= 1024.0
    return f"{number:.1f} PiB{suffix}"


def format_rate(bytes_per_second: float) -> str:
    return format_bytes(bytes_per_second, suffix="/s")


def format_duration(seconds: float | int) -> str:
    total = int(max(0, seconds))
    days, remainder = divmod(total, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def mask_secret(value: str, *, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "•" * len(value)
    return "•" * min(12, max(4, len(value) - visible)) + value[-visible:]


# ---------------------------------------------------------------------------
# OS / network
# ---------------------------------------------------------------------------
def parse_os_release(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def parse_resolv_conf(text: str) -> list[str]:
    servers: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver" and parts[1] not in servers:
            servers.append(parts[1])
    return servers


@dataclass(frozen=True, slots=True)
class WifiNetwork:
    ssid: str
    bssid: str
    signal: int
    security: str
    in_use: bool
    channel: str = ""

    @property
    def is_open(self) -> bool:
        normalized = self.security.strip().lower()
        return normalized in {"", "--", "open", "none"}

    @property
    def display_security(self) -> str:
        return "Open" if self.is_open else self.security


def parse_nmcli_escaped(line: str) -> list[str]:
    """Split one line of ``nmcli -t --escape yes`` output."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def parse_nmcli_wifi(text: str) -> list[WifiNetwork]:
    """Parse ``nmcli -t -f IN-USE,SSID,BSSID,SIGNAL,SECURITY device wifi list``."""
    best: dict[str, WifiNetwork] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = parse_nmcli_escaped(line)
        if len(parts) < 5:
            continue
        in_use_raw, ssid, bssid, signal_raw, security = (p.strip() for p in parts[:5])
        ssid = ssid or "<hidden>"
        try:
            signal = int(signal_raw)
        except ValueError:
            signal = 0
        network = WifiNetwork(
            ssid=ssid,
            bssid=bssid,
            signal=signal,
            security=security,
            in_use=in_use_raw == "*",
            channel=parts[5].strip() if len(parts) > 5 else "",
        )
        previous = best.get(network.ssid)
        if previous is None or network.signal > previous.signal:
            best[network.ssid] = network
    return sorted(best.values(), key=lambda n: (not n.in_use, -n.signal, n.ssid.lower()))


@dataclass(frozen=True, slots=True)
class NmDevice:
    device: str
    kind: str
    state: str
    connection: str


def parse_nmcli_devices(text: str) -> list[NmDevice]:
    result: list[NmDevice] = []
    for line in text.splitlines():
        parts = parse_nmcli_escaped(line)
        if len(parts) < 4:
            continue
        result.append(NmDevice(parts[0], parts[1], parts[2], parts[3]))
    return result


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FsEntry:
    source: str
    size: str
    used: str
    available: str
    percent: int
    mount: str


def parse_df(text: str) -> list[FsEntry]:
    entries: list[FsEntry] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        source, size, used, available, percent_raw = parts[:5]
        mount = " ".join(parts[5:])
        try:
            percent = int(percent_raw.rstrip("%"))
        except ValueError:
            percent = 0
        entries.append(FsEntry(source, size, used, available, percent, mount))
    return entries


# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Package:
    repo: str
    name: str
    version: str
    description: str
    installed: bool = False

    @property
    def source(self) -> str:
        return "AUR" if self.repo == "aur" else self.repo


_PACKAGE_HEADER = re.compile(
    r"^(?P<repo>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9@._+-]+)\s+"
    r"(?P<version>[^\s]+)(?P<flags>(?:\s+\[[^\]]*\])*)"
)


def parse_pacman_search(text: str, *, limit: int = 200) -> list[Package]:
    """Parse ``pacman -Ss`` / ``yay -Ss`` output."""
    packages: list[Package] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines) and len(packages) < limit:
        line = lines[index]
        match = _PACKAGE_HEADER.match(line.strip())
        if not match:
            index += 1
            continue
        description_parts: list[str] = []
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                index += 1
                if description_parts:
                    break
                continue
            if _PACKAGE_HEADER.match(candidate.strip()):
                break
            description_parts.append(candidate.strip())
            index += 1
            if len(" ".join(description_parts)) > 220:
                break
        description = " ".join(description_parts)
        if len(description) > 200:
            description = description[:197] + "…"
        flags = match.group("flags") or ""
        packages.append(
            Package(
                repo=match.group("repo"),
                name=match.group("name"),
                version=match.group("version"),
                description=description,
                installed="installed" in flags.lower(),
            )
        )
    return packages


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    name: str
    old_version: str
    new_version: str


def parse_pacman_updates(text: str) -> list[UpdateInfo]:
    updates: list[UpdateInfo] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[-2] == "->":
            updates.append(UpdateInfo(parts[0], parts[1], parts[3]))
    return updates


# ---------------------------------------------------------------------------
# systemd / ports / logins
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SystemdUnit:
    unit: str
    load: str
    active: str
    sub: str
    description: str


def parse_systemd_units(text: str) -> list[SystemdUnit]:
    units: list[SystemdUnit] = []
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        if not parts[0].endswith((".service", ".socket", ".timer", ".mount")):
            continue
        units.append(
            SystemdUnit(
                unit=parts[0],
                load=parts[1],
                active=parts[2],
                sub=parts[3],
                description=parts[4].strip() if len(parts) > 4 else "",
            )
        )
    return units


@dataclass(frozen=True, slots=True)
class PortInfo:
    protocol: str
    state: str
    address: str
    port: int | None
    process: str

    @property
    def exposed(self) -> bool:
        return self.address not in {"127.0.0.1", "::1", "localhost"}

    @property
    def endpoint(self) -> str:
        return f"{self.address}:{self.port}" if self.port is not None else self.address


def parse_ss_ports(text: str) -> list[PortInfo]:
    ports: list[PortInfo] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] in {"Netid", "State"}:
            continue
        protocol, state = parts[0], parts[1]
        local = parts[4]
        process = " ".join(parts[6:]) if len(parts) > 6 else ""
        address, port = _split_endpoint(local)
        ports.append(PortInfo(protocol, state, address, port, process))
    return ports


def _split_endpoint(value: str) -> tuple[str, int | None]:
    if value.startswith("["):
        closing = value.find("]")
        if closing != -1:
            address = value[1:closing]
            remainder = value[closing + 1 :]
            port = remainder[1:] if remainder.startswith(":") else ""
            try:
                return address, int(port)
            except ValueError:
                return address, None
    if ":" in value:
        address, port = value.rsplit(":", 1)
        try:
            return address, int(port)
        except ValueError:
            return address, None
    return value, None


@dataclass(frozen=True, slots=True)
class LoginRecord:
    user: str
    terminal: str
    host: str
    date: str


def parse_last_logins(text: str) -> list[LoginRecord]:
    records: list[LoginRecord] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("wtmp", "btmp", "reboot")):
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        records.append(
            LoginRecord(
                user=parts[0],
                terminal=parts[1],
                host=parts[2] if len(parts) > 2 else "",
                date=" ".join(parts[3:7]),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BluetoothDevice:
    address: str
    name: str
    paired: bool = False
    connected: bool = False
    trusted: bool = False


def parse_bluetooth_pairs(text: str) -> list[BluetoothDevice]:
    """Parse ``bluetoothctl devices`` lines (``Device AA:.. Name``)."""
    devices: list[BluetoothDevice] = []
    for line in text.splitlines():
        match = re.match(r"^Device\s+([0-9A-Fa-f:]{17})\s*(.*)$", line.strip())
        if match:
            devices.append(BluetoothDevice(match.group(1), match.group(2) or "Unknown"))
    return devices


def parse_bluetooth_info(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Hyprland
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class HyprMonitor:
    name: str
    description: str
    width: int
    height: int
    refresh: float
    x: int
    y: int
    scale: float
    focused: bool
    dpms: bool

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height} @ {self.refresh:.0f} Hz"


def parse_hypr_monitors(text: str) -> list[HyprMonitor]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    monitors: list[HyprMonitor] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        monitors.append(
            HyprMonitor(
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                width=int(item.get("width", 0) or 0),
                height=int(item.get("height", 0) or 0),
                refresh=float(item.get("refreshRate", 0) or 0),
                x=int(item.get("x", 0) or 0),
                y=int(item.get("y", 0) or 0),
                scale=float(item.get("scale", 1) or 1),
                focused=bool(item.get("focused", False)),
                dpms=bool(item.get("dpmsStatus", True)),
            )
        )
    return monitors


def parse_getoption(text: str) -> int | float | str | bool | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("int", "float", "str"):
        if key in data:
            return data[key]
    if "custom" in data:
        return str(data["custom"])
    return None


def parse_config_errors(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return [line for line in text.splitlines() if line.strip()]
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    if isinstance(data, dict):
        return [str(item) for item in data.values() if str(item).strip()]
    return []


def parse_monitor_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(line_index, line)`` for monitor rules in a Hyprland config."""
    result: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("monitor=") or stripped.startswith("monitor ="):
            result.append((index, line))
    return result


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def parse_lspci(text: str) -> list[str]:
    """Return human-readable display controllers from ``lspci`` output."""
    gpus: list[str] = []
    pattern = re.compile(
        r"^\S+\s+(?:VGA compatible controller|3D controller|Display controller)"
        r"(?:\s*\[[^\]]+\])?:\s*(.+)$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        description = re.sub(r"\(rev [^)]+\)", "", match.group(1)).strip()
        if description:
            gpus.append(description)
    return gpus


def parse_sysfs_battery(percent_raw: str, status_raw: str) -> tuple[int, str]:
    try:
        percent = max(0, min(100, int(percent_raw.strip())))
    except (ValueError, AttributeError):
        percent = 0
    return percent, status_raw.strip() or "Unknown"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9@._+-]+$")


def validate_package_name(name: str) -> bool:
    name = name.strip()
    return (
        bool(name)
        and not name.startswith("-")
        and len(name) <= 128
        and bool(_PACKAGE_NAME.fullmatch(name))
    )


def validate_wifi_ssid(ssid: str) -> bool:
    if not ssid or len(ssid.encode("utf-8", errors="replace")) > 32:
        return False
    return not any(ord(char) < 32 or ord(char) == 127 for char in ssid)


def validate_wifi_password(password: str) -> bool:
    return len(password) <= 63 and "\x00" not in password
