"""Network page: interfaces, traffic, DNS and WiFi."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QTreeWidgetItem,
)

from ...core import network
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.parsers import format_bytes, format_rate
from ...core.privileged import launch_in_terminal
from ...core.stats import Stats
from ..theme import Palette
from ..widgets import (
    BasePage,
    Card,
    DataTable,
    Sparkline,
    ask_text,
)


class NetworkPage(BasePage):
    title = "Network"
    subtitle = "Interfaces, DNS and WiFi"
    icon_name = "network-workgroup-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_DriveNetIcon

    def __init__(
        self,
        runner: CommandRunner,
        settings: Settings,
        *,
        palette: Palette,
        mono_font: str = "Monospace",
        parent=None,
    ) -> None:
        super().__init__(runner, settings, mono_font=mono_font, parent=parent)
        self.palette = palette
        self._loaded = False
        self._networks: list = []
        self._scan_requested = False

        self.add_action_button(
            "Refresh",
            self.refresh_all,
            icon="view-refresh",
            style="Primary",
            tooltip="Refresh interfaces and network status",
        )

        # Status ---------------------------------------------------------
        status_card = Card("Connection status")
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(18)
        status_grid.setVerticalSpacing(6)
        self.nm_value = self._status_row(status_grid, 0, "NetworkManager")
        self.radio_value = self._status_row(status_grid, 1, "WiFi radio")
        self.device_value = self._status_row(status_grid, 2, "WiFi device")
        self.connection_value = self._status_row(status_grid, 3, "Active connection")
        status_card.add_layout(status_grid)
        self.start_nm_btn = QPushButton("Start NetworkManager")
        self.start_nm_btn.setObjectName("Primary")
        self.start_nm_btn.clicked.connect(self.start_networkmanager)
        status_card.add_action(self.start_nm_btn)
        self.add(status_card)

        # Interfaces -----------------------------------------------------
        self.add_section("Interfaces")
        iface_card = Card()
        self.iface_table = DataTable(
            ["Interface", "State", "IPv4", "IPv6", "MAC", "Speed"],
            stretch_column=2,
            min_height=150,
        )
        iface_card.add(self.iface_table)
        row = QHBoxLayout()
        self.iface_refresh = QPushButton("Refresh interfaces")
        self.iface_refresh.setObjectName("Ghost")
        self.iface_refresh.clicked.connect(self.refresh_all)
        row.addWidget(self.iface_refresh)
        row.addStretch()
        iface_card.add_layout(row)
        self.add(iface_card)

        # Traffic --------------------------------------------------------
        self.add_section("Traffic")
        traffic = Card("Live throughput")
        self.down_value = QLabel("—")
        self.down_value.setObjectName("StatValue")
        self.up_value = QLabel("—")
        self.up_value.setObjectName("StatValue")
        traffic_grid = QGridLayout()
        traffic_grid.setHorizontalSpacing(24)
        traffic_grid.setVerticalSpacing(4)
        traffic_grid.addWidget(self._caption("Download"), 0, 0)
        traffic_grid.addWidget(self._caption("Upload"), 0, 1)
        traffic_grid.addWidget(self.down_value, 1, 0)
        traffic_grid.addWidget(self.up_value, 1, 1)
        traffic.add_layout(traffic_grid)
        self.net_spark = Sparkline(samples=80)
        self.net_spark.set_colour(palette.info)
        traffic.add(self.net_spark)
        self.total_traffic = QLabel("")
        self.total_traffic.setObjectName("Hint")
        traffic.add(self.total_traffic)
        self.add(traffic)

        # DNS ------------------------------------------------------------
        self.add_section("DNS")
        dns_card = Card("System resolver")
        self.dns_label = QLabel("Loading…")
        self.dns_label.setObjectName("Muted")
        self.dns_label.setWordWrap(True)
        self.dns_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dns_card.add(self.dns_label)
        dns_buttons = QHBoxLayout()
        dns_buttons.setSpacing(8)
        set_dns = QPushButton("Use Cloudflare DNS")
        set_dns.clicked.connect(self.apply_cloudflare_dns)
        flush = QPushButton("Flush DNS cache")
        flush.clicked.connect(self.flush_dns_cache)
        dns_buttons.addWidget(set_dns)
        dns_buttons.addWidget(flush)
        dns_buttons.addStretch()
        dns_card.add_layout(dns_buttons)
        self.add(dns_card)

        # WiFi -----------------------------------------------------------
        self.add_section("WiFi")
        wifi_card = Card()
        self.wifi_status = QLabel("Checking NetworkManager…")
        self.wifi_status.setObjectName("Muted")
        self.wifi_status.setWordWrap(True)
        wifi_card.add(self.wifi_status)

        self.wifi_list = QListWidget()
        self.wifi_list.setMinimumHeight(180)
        self.wifi_list.setAlternatingRowColors(True)
        self.wifi_list.itemDoubleClicked.connect(lambda _item: self.connect_selected())
        wifi_card.add(self.wifi_list)

        wifi_buttons = QHBoxLayout()
        wifi_buttons.setSpacing(8)
        self.scan_btn = QPushButton("Scan networks")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.scan_networks)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_selected)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.toggle_btn = QPushButton("Toggle radio")
        self.toggle_btn.clicked.connect(self.toggle_radio)
        for button in (self.scan_btn, self.connect_btn, self.disconnect_btn, self.toggle_btn):
            wifi_buttons.addWidget(button)
        wifi_buttons.addStretch()
        wifi_card.add_layout(wifi_buttons)
        self.add(wifi_card)

        # Quick actions --------------------------------------------------
        self.add_section("Quick actions")
        quick = Card()
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        ping_btn = QPushButton("Ping 1.1.1.1")
        ping_btn.clicked.connect(self.ping_cloudflare)
        nmtui_btn = QPushButton("Open nmtui")
        nmtui_btn.clicked.connect(self.open_nmtui)
        quick_row.addWidget(ping_btn)
        quick_row.addWidget(nmtui_btn)
        quick_row.addStretch()
        quick.add_layout(quick_row)
        self.ping_result = QLabel("")
        self.ping_result.setObjectName("Hint")
        self.ping_result.setWordWrap(True)
        quick.add(self.ping_result)
        self.add(quick)
        self.add_stretch()

    def set_palette(self, palette: Palette) -> None:
        self.palette = palette
        self.net_spark.set_colour(palette.info)

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("StatTitle")
        return label

    def _status_row(self, grid: QGridLayout, row: int, title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("Muted")
        value = QLabel("…")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value.setWordWrap(True)
        grid.addWidget(label, row, 0)
        grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        return value

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh_all()

    def refresh_all(self) -> None:
        self.iface_refresh.setEnabled(False)

        def snapshot() -> dict[str, Any]:
            return {
                "nm": network.networkmanager_active(),
                "radio": network.wifi_radio(),
                "device": network.wifi_device(),
                "interfaces": network.interfaces(),
                "dns": network.dns_status(),
            }

        def apply(data: dict[str, Any]) -> None:
            self.iface_refresh.setEnabled(True)
            self._apply_snapshot(data)

        self.call(snapshot, apply)

    def _apply_snapshot(self, data: dict[str, Any]) -> None:
        nm_ok, nm_state = data["nm"]
        if nm_ok is None:
            self.nm_value.setText("unavailable")
        else:
            self.nm_value.setText("active" if nm_ok else f"inactive ({nm_state})")
        self.start_nm_btn.setVisible(not bool(nm_ok))

        radio_ok, radio_state = data["radio"]
        self.radio_value.setText(radio_state if radio_ok is not None else "unavailable")
        self.toggle_btn.setEnabled(radio_ok is not None)

        device, device_error = data["device"]
        if device is None:
            self.device_value.setText(device_error or "not found")
            connection = "—"
        else:
            self.device_value.setText(f"{device.device} · {device.state}")
            connection = (
                device.connection if device.connection not in {"", "--"} else "not connected"
            )
        self.connection_value.setText(connection)
        self.wifi_status.setText(
            "NetworkManager is not running. Start it to manage WiFi."
            if nm_ok is False
            else (
                f"Device {device.device} · {device.state} · {connection}"
                if device
                else "No WiFi adapter detected."
            )
        )
        for button in (self.scan_btn, self.connect_btn, self.disconnect_btn):
            button.setEnabled(bool(nm_ok) and device is not None)

        self.iface_table.clear_rows()
        for entry in data["interfaces"]:
            self.iface_table.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        entry.name,
                        entry.state,
                        entry.ipv4,
                        entry.ipv6,
                        entry.mac,
                        f"{entry.speed} Mb/s" if entry.speed else "—",
                    ]
                )
            )

        _servers, details = data["dns"]
        self.dns_label.setText(details or "No resolver information available.")

    def scan_networks(self) -> None:
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning…")

        def done(result) -> None:
            networks, error = result
            self.scan_btn.setText("Scan networks")
            self.scan_btn.setEnabled(True)
            self.wifi_list.clear()
            self._networks = networks
            if error:
                self.wifi_list.addItem(error)
                return
            if not networks:
                self.wifi_list.addItem("No visible networks found.")
                return
            for network_entry in networks:
                bars = self._signal_bars(network_entry.signal)
                lock = "" if network_entry.is_open else "  🔒"
                prefix = "● " if network_entry.in_use else "  "
                item = QListWidgetItem(
                    f"{prefix}{bars}  {network_entry.ssid}{lock}   "
                    f"{network_entry.signal}%  {network_entry.display_security}"
                )
                item.setData(Qt.ItemDataRole.UserRole, network_entry.ssid)
                item.setData(Qt.ItemDataRole.UserRole + 1, network_entry.bssid)
                item.setData(Qt.ItemDataRole.UserRole + 2, network_entry.security)
                item.setToolTip(f"BSSID: {network_entry.bssid}")
                self.wifi_list.addItem(item)

        self.call(network.scan_wifi, done)

    @staticmethod
    def _signal_bars(signal: int) -> str:
        if signal >= 75:
            return "▂▄▆█"
        if signal >= 50:
            return "▂▄▆_"
        if signal >= 25:
            return "▂▄__"
        return "▂___"

    def connect_selected(self) -> None:
        item = self.wifi_list.currentItem()
        if item is None:
            self.notify("Select a network first.", "info")
            return
        ssid = item.data(Qt.ItemDataRole.UserRole)
        bssid = item.data(Qt.ItemDataRole.UserRole + 1) or ""
        security = (item.data(Qt.ItemDataRole.UserRole + 2) or "").lower()
        if not ssid:
            self.notify("That entry is not a connectable network.", "warning")
            return

        password = ""
        if security not in {"", "--", "open", "none"}:
            entered = ask_text(
                self,
                "WiFi password",
                f"Password for “{ssid}”\nLeave empty to use a saved profile:",
                password=True,
            )
            if entered is None:
                return
            password = entered

        self.notify(f"Connecting to {ssid}…", "info")

        def done(result) -> None:
            if result.ok:
                self.notify(f"Connected to {ssid}.", "success")
            self.refresh_all()
            if not result.ok:
                self.notify(result.summary(), "error")

        self.run_command(
            ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
            + (["bssid", bssid] if bssid else [])
            + (["password", password] if password else []),
            done,
            timeout=45,
            busy=self.connect_btn,
            busy_text="Connecting…",
            report_errors=False,
        )

    def disconnect(self) -> None:
        def done(result) -> None:
            if result.ok:
                self.notify("WiFi disconnected.", "success")
            self.refresh_all()

        self.call(network.disconnect_wifi, done)

    def toggle_radio(self) -> None:
        self.call(network.toggle_wifi, self._after_toggle)

    def _after_toggle(self, outcome: tuple[bool, str]) -> None:
        ok, message = outcome
        self.notify(message, "success" if ok else "error")
        self.refresh_all()

    def start_networkmanager(self) -> None:
        def done(result) -> None:
            self.notify(
                "NetworkManager started." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh_all()

        self.call(network.start_networkmanager, done)

    def apply_cloudflare_dns(self) -> None:
        if not self.confirm(
            "Change DNS",
            "Set DNS servers to 1.1.1.1 and 8.8.8.8?\n\n"
            "On systems using systemd-resolved this is applied to the active link.",
            ok_text="Set DNS",
        ):
            return

        def done(result) -> None:
            self.notify(
                "DNS servers updated." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh_all()

        self.call(lambda: network.set_dns(["1.1.1.1", "8.8.8.8"]), done)

    def flush_dns_cache(self) -> None:
        def done(result) -> None:
            self.notify(
                "DNS cache flushed." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )

        self.call(network.flush_dns, done)

    def ping_cloudflare(self) -> None:
        self.ping_result.setText("Pinging 1.1.1.1…")

        def done(result) -> None:
            if result.ok:
                self.ping_result.setText(" ".join(result.stdout.splitlines()[-2:]))
                self.notify("Ping finished.", "success")
            else:
                self.ping_result.setText(result.summary())
                self.notify(result.summary(), "error")

        self.call(network.ping, done)

    def open_nmtui(self) -> None:
        ok, error = launch_in_terminal(
            ["nmtui"],
            title="NetworkManager TUI",
            terminal=self.settings.terminal,
        )
        if not ok:
            self.notify(error, "error")

    # ------------------------------------------------------------------
    def update_stats(self, stats: Stats) -> None:
        self.down_value.setText(format_rate(stats.net_down))
        self.up_value.setText(format_rate(stats.net_up))
        self.total_traffic.setText(
            f"Total received {format_bytes(stats.net_recv_total)} · "
            f"sent {format_bytes(stats.net_sent_total)}"
        )
        self.net_spark.append(stats.net_down + stats.net_up)
