"""Firewall, SSH, login history and listening port helpers."""

from __future__ import annotations

import glob
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandResult, run, which
from .fs import read_text
from .parsers import LoginRecord, PortInfo, parse_last_logins, parse_ss_ports
from .privileged import run_privileged

__all__ = [
    "FirewallStatus",
    "SshConfig",
    "firewall_action",
    "firewall_status",
    "listening_ports",
    "login_history",
    "security_checks",
    "ssh_config",
    "ssh_keys",
    "ssh_service_action",
    "ssh_status",
]


@dataclass(frozen=True, slots=True)
class FirewallStatus:
    backend: str
    active: bool | None
    detail: str


@dataclass(frozen=True, slots=True)
class SshConfig:
    permit_root_login: str
    password_authentication: str
    port: str
    files: str


def firewall_status() -> FirewallStatus:
    if which("ufw"):
        result = run_privileged(["ufw", "status"], timeout=12, allow_prompt=False)
        text = result.output or "requires administrator rights"
        active = None
        if result.ok:
            lowered = result.stdout.lower()
            active = "status: active" in lowered
        return FirewallStatus("ufw", active, text)
    if which("firewall-cmd"):
        result = run(["firewall-cmd", "--state"], timeout=8)
        active = result.ok and "running" in result.stdout.lower()
        return FirewallStatus("firewalld", active, result.output or result.summary())
    if which("nft"):
        result = run_privileged(["nft", "list", "ruleset"], timeout=10, allow_prompt=False)
        if result.ok:
            active = bool(result.stdout.strip())
            detail = result.output or "No nftables rules loaded"
        else:
            active = None
            detail = "Ruleset requires administrator rights (use Show status)."
        return FirewallStatus("nftables", active, detail)
    return FirewallStatus("", None, "No supported firewall found (ufw, firewalld or nftables).")


def firewall_action(action: str) -> CommandResult:
    if which("ufw"):
        commands = {
            "enable": ["ufw", "enable"],
            "disable": ["ufw", "disable"],
            "allow-ssh": ["ufw", "allow", "22/tcp"],
            "status": ["ufw", "status", "verbose"],
            "reload": ["ufw", "reload"],
        }
        if action not in commands:
            return CommandResult((), 2, error=f"Unsupported firewall action: {action}")
        return run_privileged(commands[action], timeout=45)
    if which("firewall-cmd"):
        commands = {
            "enable": ["firewall-cmd", "--reload"],
            "disable": ["systemctl", "stop", "firewalld"],
            "allow-ssh": ["firewall-cmd", "--permanent", "--add-service=ssh"],
            "status": ["firewall-cmd", "--list-all"],
            "reload": ["firewall-cmd", "--reload"],
        }
        if action not in commands:
            return CommandResult((), 2, error=f"Unsupported firewall action: {action}")
        return run_privileged(commands[action], timeout=45)
    return CommandResult((), 127, error="No supported firewall found.")


def ssh_status() -> str:
    fallback = ""
    for unit in ("sshd", "ssh"):
        result = run(["systemctl", "is-active", unit], timeout=6)
        state = result.stdout.strip()
        if state == "active":
            return "active"
        if state and state != "inactive" and not fallback:
            fallback = state
    return fallback or "inactive"


def _sshd_config_files() -> list[str]:
    files = ["/etc/ssh/sshd_config"]
    files += sorted(glob.glob("/etc/ssh/sshd_config.d/*.conf"))
    files += sorted(glob.glob("/etc/ssh/sshd_config.d/*.conf.d/*.conf"))
    return [path for path in files if Path(path).is_file()]


def ssh_config() -> SshConfig:
    values: dict[str, str] = {}
    files = _sshd_config_files()
    for path in files:
        for line in read_text(path).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split(None, 1)
            if len(parts) == 2 and parts[0].lower() in {
                "permitrootlogin",
                "passwordauthentication",
                "port",
            }:
                values[parts[0].lower()] = parts[1].strip()
    return SshConfig(
        permit_root_login=values.get("permitrootlogin", "not set"),
        password_authentication=values.get("passwordauthentication", "not set"),
        port=values.get("port", "22"),
        files=", ".join(Path(path).name for path in files) or "not found",
    )


def ssh_keys() -> list[tuple[str, str, str]]:
    directory = Path.home() / ".ssh"
    if not directory.is_dir():
        return []
    entries: list[tuple[str, str, str]] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        try:
            mode = stat.filemode(path.stat().st_mode)
        except OSError:
            mode = "?"
        entries.append((path.name, mode, "public" if path.suffix == ".pub" else "private"))
    return entries


def login_history(limit: int = 10) -> tuple[list[LoginRecord], list[str]]:
    last = run(["last", "-n", str(limit)], timeout=8)
    logins = parse_last_logins(last.stdout) if last.ok else []
    failed: list[str] = []
    lastb = run_privileged(["lastb", "-n", "8"], timeout=8, allow_prompt=False)
    if lastb.ok:
        failed = [line.strip() for line in lastb.stdout.splitlines() if line.strip()][:8]
    return logins, failed


def listening_ports() -> list[PortInfo]:
    result = run(["ss", "-tulpn"], timeout=8)
    if not result.ok:
        return []
    return parse_ss_ports(result.stdout)


def ssh_service_action(action: str) -> CommandResult:
    if action not in {"start", "stop", "restart", "enable", "disable"}:
        return CommandResult((), 2, error=f"Unsupported SSH action: {action}")
    unit = (
        "sshd" if which("sshd") or Path("/usr/lib/systemd/system/sshd.service").exists() else "ssh"
    )
    return run_privileged(["systemctl", action, unit], timeout=45)


def security_checks() -> list[tuple[str, str, str]]:
    """Return ``(label, level, detail)`` where level is ok/warn/info."""
    checks: list[tuple[str, str, str]] = []
    firewall = firewall_status()
    if firewall.active is True:
        checks.append(("Firewall active", "ok", firewall.backend))
    elif firewall.active is False:
        checks.append(("Firewall inactive", "warn", firewall.backend))
    else:
        checks.append(
            (
                "Firewall status",
                "info",
                firewall.detail.splitlines()[0] if firewall.detail else "unknown",
            )
        )

    config = ssh_config()
    if config.permit_root_login.lower() in {"no", "prohibit-password"}:
        checks.append(("SSH root login disabled", "ok", config.permit_root_login))
    else:
        checks.append(("SSH root login", "warn", config.permit_root_login))
    if config.password_authentication.lower() == "no":
        checks.append(("SSH password login disabled", "ok", "key-based login"))
    else:
        checks.append(("SSH password login", "info", config.password_authentication))

    if Path("/sys/firmware/efi").exists():
        checks.append(("UEFI boot", "info", "Secure Boot status not inspected"))
    lsblk = run(["lsblk", "-o", "FSTYPE", "-n"], timeout=6)
    if "crypto_LUKS" in lsblk.stdout:
        checks.append(("Disk encryption", "ok", "LUKS detected"))
    else:
        checks.append(("Disk encryption", "info", "No LUKS volume detected"))
    return checks


def ssh_authorized_keys_count() -> int:
    path = Path.home() / ".ssh" / "authorized_keys"
    if not path.is_file():
        return 0
    return len(
        [line for line in read_text(path).splitlines() if line.strip() and not line.startswith("#")]
    )


def _strip_comment(value: str) -> str:
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def home_ssh_permissions() -> str:
    directory = Path.home() / ".ssh"
    if not directory.is_dir():
        return "missing"
    try:
        return oct(directory.stat().st_mode & 0o777)
    except OSError:
        return "?"


def session_user() -> str:
    return os.environ.get("USER", os.environ.get("LOGNAME", ""))
