"""Power page: battery, profiles and session actions."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStyle,
    QWidget,
)

from ...core import power
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.parsers import format_duration
from ...core.stats import Stats
from ..widgets import BasePage, Card, KeyValueGrid

_ACTIONS = (
    ("Lock", "lock", "Lock the session", ""),
    ("Suspend", "suspend", "Suspend to RAM", ""),
    ("Hibernate", "hibernate", "Suspend to disk", ""),
    ("Log out", "logout", "Close the Hyprland session", ""),
    ("Reboot", "reboot", "Restart the computer", "Danger"),
    ("Shut down", "shutdown", "Power the computer off", "Danger"),
)


class PowerPage(BasePage):
    title = "Power"
    subtitle = "Battery, performance profile and session actions"
    icon_name = "battery-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_DialogApplyButton

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
        self._profiles_loaded = False

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Ghost",
            tooltip="Re-read battery and power profile",
        )

        # Battery --------------------------------------------------------
        self.add_section("Battery")
        battery_card = Card("Battery status")
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setValue(0)
        self.battery_bar.setTextVisible(False)
        battery_card.add(self.battery_bar)
        self.battery_grid = KeyValueGrid()
        self.battery_percent = self.battery_grid.add("Charge", "—")
        self.battery_status = self.battery_grid.add("Status", "—")
        self.battery_time = self.battery_grid.add("Remaining", "—")
        self.battery_source = self.battery_grid.add("Power source", "—")
        battery_card.add(self.battery_grid)
        self.no_battery = QLabel("No battery detected — this looks like a desktop.")
        self.no_battery.setObjectName("Hint")
        battery_card.add(self.no_battery)
        self.add(battery_card)

        # Power profile --------------------------------------------------
        self.add_section("Performance")
        profile_card = Card("Power profiles")
        self.profile_row = QWidget()
        row = QHBoxLayout(self.profile_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(180)
        self.profile_combo.setEnabled(False)
        self.apply_profile_btn = QPushButton("Apply profile")
        self.apply_profile_btn.setObjectName("Primary")
        self.apply_profile_btn.clicked.connect(self.apply_profile)
        row.addWidget(QLabel("Profile"))
        row.addWidget(self.profile_combo)
        row.addWidget(self.apply_profile_btn)
        row.addStretch()
        profile_card.add(self.profile_row)
        self.profile_hint = QLabel("Checking power profiles…")
        self.profile_hint.setObjectName("Hint")
        self.profile_hint.setWordWrap(True)
        profile_card.add(self.profile_hint)
        self.add(profile_card)

        # Actions --------------------------------------------------------
        self.add_section("Session")
        actions_card = Card("System actions")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.action_buttons: dict[str, QPushButton] = {}
        for index, (label, action, tooltip, style) in enumerate(_ACTIONS):
            button = QPushButton(label)
            button.setToolTip(tooltip)
            if style:
                button.setObjectName(style)
            if action == "hibernate":
                button.setEnabled(power.can_hibernate())
            button.clicked.connect(
                lambda _checked=False, a=action, name=label: self.run_action(a, name)
            )
            grid.addWidget(button, index // 3, index % 3)
            self.action_buttons[action] = button
        actions_card.add_layout(grid)
        self.add(actions_card)
        self.add_stretch()

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        self.refresh_profiles()

    def refresh_profiles(self) -> None:
        if self._profiles_loaded:
            return

        def work():
            return power.available_profiles(), power.current_profile()

        def done(values) -> None:
            profiles, current = values
            self.profile_combo.clear()
            self._profiles_loaded = True
            if not profiles:
                self.profile_row.setVisible(False)
                self.profile_hint.setText(
                    "power-profiles-daemon is not installed. Install it to switch "
                    "between power-saver, balanced and performance."
                )
                return
            self.profile_row.setVisible(True)
            self.profile_combo.addItems(profiles)
            if current in profiles:
                self.profile_combo.setCurrentText(current)
            self.profile_combo.setEnabled(True)
            self.apply_profile_btn.setEnabled(True)
            self.profile_hint.setText(f"Active profile: {current or 'unknown'}")

        self.call(work, done)

    def apply_profile(self) -> None:
        profile = self.profile_combo.currentText()
        if not profile:
            return

        def done(result) -> None:
            if result.ok:
                self.profile_hint.setText(f"Active profile: {profile}")
                self.notify(f"Power profile set to {profile}.", "success")
            else:
                self.notify(result.summary(), "error")

        self.run_command(
            ["powerprofilesctl", "set", profile],
            done,
            busy=self.apply_profile_btn,
            busy_text="Applying…",
            report_errors=False,
        )

    # ------------------------------------------------------------------
    def update_stats(self, stats: Stats) -> None:
        battery = stats.battery
        if battery is None:
            self.battery_bar.setVisible(False)
            self.battery_grid.setVisible(False)
            self.no_battery.setVisible(True)
            return
        self.no_battery.setVisible(False)
        self.battery_grid.setVisible(True)
        self.battery_bar.setVisible(True)
        self.battery_bar.setValue(battery.percent)
        self.battery_percent.setText(f"{battery.percent}%")
        self.battery_status.setText(battery.status)
        self.battery_time.setText(
            format_duration(battery.seconds_left) if battery.seconds_left else "—"
        )
        if battery.plugged is None:
            source = "Unknown"
        else:
            source = "AC adapter" if battery.plugged else "Battery"
        self.battery_source.setText(source)

    # ------------------------------------------------------------------
    def run_action(self, action: str, label: str) -> None:
        descriptions = {
            "lock": "Lock the session now?",
            "suspend": "Suspend the computer now?",
            "hibernate": "Hibernate the computer now?\n\nUnsaved work is written to disk.",
            "logout": "Log out of Hyprland? All applications will be closed.",
            "reboot": "Reboot the computer now? All applications will be closed.",
            "shutdown": "Shut down the computer now? All applications will be closed.",
        }
        if not self.confirm(
            label,
            descriptions.get(action, f"Perform “{label}”?"),
            danger=action in {"reboot", "shutdown", "logout"},
            ok_text=label,
        ):
            return

        button = self.action_buttons.get(action)
        if button is not None:
            button.setEnabled(False)

        def done(result) -> None:
            if button is not None:
                button.setEnabled(True)
            if not result.ok:
                self.notify(result.summary(), "error")

        self.call(lambda: power.perform_action(action), done)
