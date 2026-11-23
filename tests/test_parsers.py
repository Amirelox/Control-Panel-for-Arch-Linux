from __future__ import annotations

import json

import pytest

from control_panel.core.parsers import (
    format_bytes,
    format_duration,
    format_rate,
    mask_secret,
    parse_bluetooth_info,
    parse_bluetooth_pairs,
    parse_config_errors,
    parse_df,
    parse_getoption,
    parse_hypr_monitors,
    parse_lspci,
    parse_monitor_lines,
    parse_nmcli_devices,
    parse_nmcli_escaped,
    parse_nmcli_wifi,
    parse_os_release,
    parse_pacman_search,
    parse_pacman_updates,
    parse_resolv_conf,
    parse_ss_ports,
    parse_sysfs_battery,
    parse_systemd_units,
    validate_package_name,
    validate_wifi_password,
    validate_wifi_ssid,
)


def test_format_helpers() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KiB"
    assert format_bytes(1024**3 * 1.5) == "1.5 GiB"
    assert format_rate(2048) == "2.0 KiB/s"
    assert format_duration(59) == "59s"
    assert format_duration(3661) == "1h 1m"
    assert format_duration(90_000) == "1d 1h"


def test_mask_secret() -> None:
    assert mask_secret("") == ""
    assert mask_secret("abc") == "•••"
    assert mask_secret("supersecretvalue").endswith("alue")


def test_os_release_and_resolv_conf() -> None:
    release = parse_os_release('NAME="Arch Linux"\nID=arch\nPRETTY_NAME="Arch Linux"\n# comment\n')
    assert release["NAME"] == "Arch Linux"
    assert release["ID"] == "arch"
    assert parse_resolv_conf("nameserver 1.1.1.1\nnameserver 8.8.8.8\n# x\n") == [
        "1.1.1.1",
        "8.8.8.8",
    ]


def test_nmcli_escaped() -> None:
    assert parse_nmcli_escaped(r"a\:b:c") == ["a:b", "c"]
    assert parse_nmcli_escaped(r"a\\b:c") == ["a\\b", "c"]
    assert parse_nmcli_escaped("plain") == ["plain"]


def test_parse_nmcli_wifi() -> None:
    output = "\n".join(
        [
            r"*:Home\:WiFi:AA\:BB\:CC\:DD\:EE\:FF:82:WPA2",
            r":Home\:WiFi:AA\:BB\:CC\:DD\:EE\:00:40:WPA2",
            r":Cafe::35:",
            r":Guest:11\:22\:33\:44\:55\:66:65:WPA1 WPA2",
        ]
    )
    networks = parse_nmcli_wifi(output)
    assert [network.ssid for network in networks] == ["Home:WiFi", "Guest", "Cafe"]
    assert networks[0].in_use is True
    assert networks[0].signal == 82
    assert networks[0].is_open is False
    assert networks[2].is_open is True


def test_parse_nmcli_devices() -> None:
    devices = parse_nmcli_devices("wlan0:wifi:connected:Home\neth0:ethernet:disconnected:--\n")
    assert devices[0].device == "wlan0"
    assert devices[1].kind == "ethernet"


def test_parse_df() -> None:
    entries = parse_df(
        "udev 7.7G 0 7.7G 0% /dev\n"
        "/dev/nvme0n1p2 465G 123G 342G 27% /\n"
        "/dev/nvme0n1p1 1G 0.5G 0.5G 50% /boot\n"
    )
    assert len(entries) == 3
    assert entries[1].percent == 27
    assert entries[1].mount == "/"


def test_parse_pacman_search() -> None:
    output = (
        "core/bash 5.3.20-1 [installed]\n"
        "    The GNU Bourne Again shell\n"
        "\n"
        "extra/argbash 2.11.0-1\n"
        "    Bash argument parsing code generator\n"
        "    More details here\n"
        "\n"
        "aur/algorithms-git 0.0.0.r1-1 (+0 0.00) (Orphaned)\n"
        "    Algorithms in Bash\n"
    )
    packages = parse_pacman_search(output)
    assert [package.name for package in packages] == ["bash", "argbash", "algorithms-git"]
    assert packages[0].installed is True
    assert packages[1].repo == "extra"
    assert packages[1].description == "Bash argument parsing code generator More details here"
    assert packages[2].source == "AUR"


def test_parse_pacman_updates() -> None:
    updates = parse_pacman_updates("bash 5.2-1 -> 5.3-1\nyay 12.4.2-1 -> 12.4.2-2\n")
    assert updates[0].name == "bash"
    assert updates[0].old_version == "5.2-1"
    assert updates[0].new_version == "5.3-1"


def test_parse_systemd_units() -> None:
    output = (
        "sshd.service loaded active running OpenSSH Daemon\n"
        "cups.socket loaded active listening CUPS Scheduler\n"
        "not-a-unit loaded active running Ignore\n"
    )
    units = parse_systemd_units(output)
    assert [unit.unit for unit in units] == ["sshd.service", "cups.socket"]
    assert units[0].description == "OpenSSH Daemon"


def test_parse_ss_ports() -> None:
    output = (
        "Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\n"
        'tcp   LISTEN 0      4096   127.0.0.1:631      0.0.0.0:* users:(("cupsd",pid=1,fd=7))\n'
        'tcp   LISTEN 0      4096   [::]:22            [::]:*    users:(("sshd",pid=2,fd=3))\n'
    )
    ports = parse_ss_ports(output)
    assert len(ports) == 2
    assert ports[0].address == "127.0.0.1"
    assert ports[0].port == 631
    assert ports[0].exposed is False
    assert ports[1].address == "::"
    assert ports[1].exposed is True


def test_bluetooth_parsers() -> None:
    devices = parse_bluetooth_pairs(
        "Device AA:BB:CC:DD:EE:FF Headphones\nDevice 11:22:33:44:55:66 Keyboard\n"
    )
    assert devices[0].name == "Headphones"
    info = parse_bluetooth_info("Name: Headphones\nPaired: yes\nConnected: no\n")
    assert info["Paired"] == "yes"


def test_hyprland_parsers() -> None:
    monitors = json.loads(
        json.dumps(
            [
                {
                    "name": "eDP-1",
                    "description": "BOE",
                    "width": 1920,
                    "height": 1080,
                    "refreshRate": 144.0,
                    "x": 0,
                    "y": 0,
                    "scale": 1,
                    "focused": True,
                    "dpmsStatus": True,
                }
            ]
        )
    )
    parsed = parse_hypr_monitors(json.dumps(monitors))
    assert parsed[0].name == "eDP-1"
    assert parsed[0].resolution == "1920x1080 @ 144 Hz"

    assert parse_getoption('{"option": "decoration:rounding", "int": 20}') == 20
    assert parse_getoption('{"option": "x", "str": "7 7 7 7"}') == "7 7 7 7"
    assert parse_config_errors('["", "bad line"]') == ["bad line"]
    assert parse_monitor_lines(
        "monitor=eDP-1,1920x1080@144,0x0,1\n# x\nmonitor = HDMI-A-1,auto\n"
    ) == [
        (0, "monitor=eDP-1,1920x1080@144,0x0,1"),
        (2, "monitor = HDMI-A-1,auto"),
    ]


def test_lspci_and_battery() -> None:
    assert parse_lspci("00:02.0 VGA compatible controller: Intel Corporation UHD (rev 02)\n") == [
        "Intel Corporation UHD"
    ]
    assert parse_sysfs_battery("87", "Discharging") == (87, "Discharging")
    assert parse_sysfs_battery("bad", "") == (0, "Unknown")


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("firefox", True),
        ("python-pip", True),
        ("lib32-glibc", True),
        ("foo@bar", True),
        ("-rf", False),
        ("foo bar", False),
        ("foo;rm", False),
        ("", False),
    ],
)
def test_validate_package_name(name: str, valid: bool) -> None:
    assert validate_package_name(name) is valid


def test_validate_wifi() -> None:
    assert validate_wifi_ssid("Home WiFi") is True
    assert validate_wifi_ssid("bad\nssid") is False
    assert validate_wifi_ssid("") is False
    assert validate_wifi_password("secret") is True
    assert validate_wifi_password("x" * 64) is False
