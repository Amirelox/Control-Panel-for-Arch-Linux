"""Bluetooth page: controller, scanning and devices."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QTreeWidgetItem,
)

from ...core import bluetooth
from ...core.commands import CommandRunner
from ...core.config import Settings
from ..widgets import BasePage, Card, DataTable, ask


class BluetoothPage(BasePage):
    title = "Bluetooth"
    subtitle = "Controller, pairing and connected devices"
    icon_name = "bluetooth-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_CommandLink

    def __init__(
        self,
        runner: CommandRunner,
        settings: Settings,
        *,
        mono_font: str = "Monospace",
        palette=None,
        parent=None,
    ) -> None:
        super().__init__(runner, settings, mono_font=mono_font, parent=parent)
        self._loaded = False
        self._scanning = False
        self._controller = None

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Ghost",
            tooltip="Reload controller and devices",
        )

        self.add_section("Controller")
        status_card = Card("Adapter")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        self.adapter_name = self._row(grid, 0, "Name")
        self.adapter_power = self._row(grid, 1, "Power")
        self.adapter_address = self._row(grid, 2, "Address")
        self.adapter_discovery = self._row(grid, 3, "Discovery")
        status_card.add_layout(grid)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.power_on_btn = QPushButton("Power on")
        self.power_on_btn.clicked.connect(lambda: self.set_power(True))
        self.power_off_btn = QPushButton("Power off")
        self.power_off_btn.clicked.connect(lambda: self.set_power(False))
        self.start_service_btn = QPushButton("Start bluetooth service")
        self.start_service_btn.setObjectName("Primary")
        self.start_service_btn.clicked.connect(self.start_service)
        self.start_service_btn.setVisible(False)
        controls.addWidget(self.power_on_btn)
        controls.addWidget(self.power_off_btn)
        controls.addWidget(self.start_service_btn)
        controls.addStretch()
        status_card.add_layout(controls)
        self.add(status_card)

        self.add_section("Devices")
        devices_card = Card()
        self.device_table = DataTable(
            ["Device", "Address", "Paired", "Connected", "Trusted"],
            stretch_column=0,
            min_height=120,
        )
        self.device_table.set_mono_columns(1, right=False)
        devices_card.add(self.device_table)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        self.scan_btn = QPushButton("Scan for devices (8 s)")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.scan_devices)
        refresh_devices = QPushButton("Refresh")
        refresh_devices.setObjectName("Ghost")
        refresh_devices.clicked.connect(self.refresh)
        scan_row.addWidget(self.scan_btn)
        scan_row.addWidget(refresh_devices)
        scan_row.addStretch()
        devices_card.add_layout(scan_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        for label, verb, style in (
            ("Connect", "connect", ""),
            ("Disconnect", "disconnect", ""),
            ("Pair", "pair", ""),
            ("Trust", "trust", ""),
            ("Remove", "remove", "Danger"),
        ):
            button = QPushButton(label)
            if style:
                button.setObjectName(style)
            button.clicked.connect(lambda _checked=False, v=verb: self.device_action(v))
            action_row.addWidget(button)
        action_row.addStretch()
        devices_card.add_layout(action_row)
        self.hint = QLabel("Select a device to manage it.")
        self.hint.setObjectName("Hint")
        devices_card.add(self.hint)
        self.add(devices_card)
        self.add_stretch()

    @staticmethod
    def _row(grid: QGridLayout, row: int, title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("Muted")
        value = QLabel("…")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(label, row, 0)
        grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        return value

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        def work():
            return bluetooth.controller(), bluetooth.devices()

        self.call(work, self._apply)

    def _apply(self, payload) -> None:
        controller, devices = payload
        self._controller = controller
        if controller.available and not controller.error:
            self.adapter_name.setText(controller.name)
            self.adapter_power.setText("On" if controller.powered else "Off")
            self.adapter_address.setText(controller.address or "—")
            self.adapter_discovery.setText("Discovering" if controller.discovering else "Idle")
        else:
            self.adapter_name.setText(controller.error or "Not available")
            self.adapter_power.setText("—")
            self.adapter_address.setText("—")
            self.adapter_discovery.setText("—")
        self.start_service_btn.setVisible(not controller.available and bluetooth.available())
        self.power_on_btn.setEnabled(controller.available)
        self.power_off_btn.setEnabled(controller.available)
        self.scan_btn.setEnabled(controller.available and controller.powered)

        self.device_table.clear_rows()
        for device in devices:
            item = QTreeWidgetItem(
                [
                    device.name,
                    device.address,
                    "Yes" if device.paired else "",
                    "Yes" if device.connected else "",
                    "Yes" if device.trusted else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, device.address)
            self.device_table.addTopLevelItem(item)
        if self.device_table.topLevelItemCount() == 0:
            self.device_table.addTopLevelItem(QTreeWidgetItem(["No devices", "", "", "", ""]))
        self.hint.setText(
            f"{len(devices)} device(s). Select one to manage it."
            if devices
            else "No devices known. Power on the adapter and scan."
        )

    # ------------------------------------------------------------------
    def set_power(self, on: bool) -> None:
        def done(result) -> None:
            self.notify(
                f"Bluetooth powered {'on' if on else 'off'}." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh()

        self.call(lambda: bluetooth.power(on), done)

    def start_service(self) -> None:
        def done(result) -> None:
            self.notify(
                "Bluetooth service started." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh()

        self.call(bluetooth.start_service, done)

    def scan_devices(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning…")
        self.hint.setText("Scanning for nearby devices. Keep the window open.")

        def done(result) -> None:
            self._scanning = False
            self.scan_btn.setText("Scan for devices (8 s)")
            self.scan_btn.setEnabled(bool(self._controller and self._controller.powered))
            if not result.ok:
                self.notify(result.summary(), "error")
            self.refresh()

        self.call(lambda: bluetooth.scan(8), done)

    def _selected_address(self) -> str | None:
        item = self.device_table.currentItem()
        if item is None:
            return None
        address = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(address, str) and address:
            return address
        return None

    def device_action(self, verb: str) -> None:
        address = self._selected_address()
        if address is None:
            self.notify("Select a device first.", "info")
            return
        name = self.device_table.currentItem().text(0)
        if verb == "remove" and not ask(
            self,
            "Remove device",
            f"Remove “{name}” ({address}) from the list?",
            danger=True,
            ok_text="Remove",
        ):
            return
        if verb in {"connect", "pair"}:
            self.notify(f"{verb.capitalize()}ing {name}…", "info")

        def done(result) -> None:
            self.notify(
                f"{name}: {verb} sent." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh()

        self.call(lambda: bluetooth.action(address, verb), done)
