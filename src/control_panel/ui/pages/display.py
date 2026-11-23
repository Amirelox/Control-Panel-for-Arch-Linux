"""Display page: brightness, monitors, DPMS and night light."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ...core import display
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.hyprland import ConfigLine, hyprctl, monitor_lines, reload, update_lines
from ...core.parsers import parse_hypr_monitors
from ..widgets import BasePage, Card, KeyValueGrid


class DisplayPage(BasePage):
    title = "Display"
    subtitle = "Brightness, monitor layout and eye comfort"
    icon_name = "video-display-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_DesktopIcon

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
        self._monitor_editors: list[tuple[ConfigLine, QLineEdit]] = []
        self._brightness_timer = QTimer(self)
        self._brightness_timer.setSingleShot(True)
        self._brightness_timer.setInterval(120)
        self._brightness_timer.timeout.connect(self._apply_brightness)

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Ghost",
            tooltip="Reload brightness and monitor information",
        )

        # Brightness -----------------------------------------------------
        self.add_section("Brightness")
        brightness_card = Card("Backlight")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.bright_slider.setRange(1, 100)
        self.bright_slider.setValue(50)
        self.bright_slider.setEnabled(False)
        self.bright_slider.valueChanged.connect(self._brightness_changed)
        self.bright_value = QLabel("—%")
        self.bright_value.setMinimumWidth(44)
        self.bright_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(QLabel("Dim"))
        row.addWidget(self.bright_slider, 1)
        row.addWidget(QLabel("Bright"))
        row.addWidget(self.bright_value)
        row_widget = QWidget()
        row_widget.setLayout(row)
        brightness_card.add(row_widget)
        self.bright_device = QLabel("Detecting backlight…")
        self.bright_device.setObjectName("Hint")
        brightness_card.add(self.bright_device)
        self.add(brightness_card)

        # Monitors -------------------------------------------------------
        self.add_section("Monitors")
        monitor_card = Card("Detected outputs")
        self.monitor_grid = KeyValueGrid()
        monitor_card.add(self.monitor_grid)
        refresh_monitors = QPushButton("Refresh detection")
        refresh_monitors.setObjectName("Ghost")
        refresh_monitors.clicked.connect(self.refresh_monitors)
        monitor_card.add_action(refresh_monitors)
        self.add(monitor_card)

        rules = Card("Hyprland monitor rules")
        self.rules_hint = QLabel("Loading monitor rules…")
        self.rules_hint.setObjectName("Hint")
        self.rules_hint.setWordWrap(True)
        rules.add(self.rules_hint)
        self.rules_box = QVBoxLayout()
        self.rules_box.setSpacing(7)
        rules.add_layout(self.rules_box)
        self.save_rules_btn = QPushButton("Save and reload")
        self.save_rules_btn.setObjectName("Primary")
        self.save_rules_btn.clicked.connect(self.save_rules)
        rules.add(self.save_rules_btn)
        self.add(rules)

        # DPMS -----------------------------------------------------------
        self.add_section("Power saving")
        dpms_card = Card("Panel power")
        dpms_row = QHBoxLayout()
        dpms_row.setSpacing(8)
        on_btn = QPushButton("Screen on")
        on_btn.clicked.connect(lambda: self._dpms(True))
        off_btn = QPushButton("Screen off")
        off_btn.clicked.connect(lambda: self._dpms(False))
        dpms_row.addWidget(on_btn)
        dpms_row.addWidget(off_btn)
        dpms_row.addStretch()
        dpms_card.add_layout(dpms_row)
        self.dpms_hint = QLabel("")
        self.dpms_hint.setObjectName("Hint")
        dpms_card.add(self.dpms_hint)
        self.add(dpms_card)

        # Night light ----------------------------------------------------
        self.add_section("Night light")
        night_card = Card("Colour temperature")
        night_row = QHBoxLayout()
        night_row.setSpacing(10)
        self.night_slider = QSlider(Qt.Orientation.Horizontal)
        self.night_slider.setRange(2500, 6500)
        self.night_slider.setSingleStep(100)
        self.night_slider.setValue(4500)
        self.night_label = QLabel("4500 K")
        self.night_label.setMinimumWidth(64)
        self.night_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.night_slider.valueChanged.connect(lambda value: self.night_label.setText(f"{value} K"))
        night_row.addWidget(QLabel("Warm"))
        night_row.addWidget(self.night_slider, 1)
        night_row.addWidget(QLabel("Cool"))
        night_row.addWidget(self.night_label)
        night_widget = QWidget()
        night_widget.setLayout(night_row)
        night_card.add(night_widget)
        night_buttons = QHBoxLayout()
        night_buttons.setSpacing(8)
        apply_night = QPushButton("Apply")
        apply_night.setObjectName("Primary")
        apply_night.clicked.connect(self.apply_night_light)
        stop_night = QPushButton("Stop")
        stop_night.clicked.connect(self.stop_night_light)
        night_buttons.addWidget(apply_night)
        night_buttons.addWidget(stop_night)
        night_buttons.addStretch()
        night_card.add_layout(night_buttons)
        self.night_hint = QLabel("")
        self.night_hint.setObjectName("Hint")
        self.night_hint.setWordWrap(True)
        night_card.add(self.night_hint)
        self.add(night_card)
        self.add_stretch()

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        self.call(display.get_brightness, self._apply_brightness_state)
        self.refresh_monitors()
        self._load_rules()
        tool = display.night_light_tool()
        self.night_hint.setText(
            f"Using {tool}." if tool else "Install wlsunset, gammastep or redshift to enable."
        )

    def _apply_brightness_state(self, state) -> None:
        if state is None:
            self.bright_slider.setEnabled(False)
            self.bright_device.setText(
                "No controllable backlight found. On desktops use the monitor's own controls."
            )
            self.bright_value.setText("—%")
            return
        self.bright_slider.blockSignals(True)
        self.bright_slider.setValue(state.percent)
        self.bright_slider.blockSignals(False)
        self.bright_slider.setEnabled(True)
        self.bright_value.setText(f"{state.percent}%")
        self.bright_device.setText(
            f"{state.device} · {state.current}/{state.maximum} · {state.backend}"
        )

    def _brightness_changed(self, value: int) -> None:
        self.bright_value.setText(f"{value}%")
        self._brightness_timer.start()

    def _apply_brightness(self) -> None:
        value = self.bright_slider.value()

        def done(result) -> None:
            if not result.ok:
                self.notify(result.summary(), "error")

        self.call(lambda: display.set_brightness(value), done)

    # ------------------------------------------------------------------
    def refresh_monitors(self) -> None:
        def done(result) -> None:
            monitors = parse_hypr_monitors(result.stdout) if result.ok else []
            self.monitor_grid.clear()
            if not monitors:
                self.monitor_grid.add(
                    "Status", result.summary(160) if not result.ok else "No outputs"
                )
                return
            for monitor in monitors:
                state = " · focused" if monitor.focused else ("" if monitor.dpms else " · dpms off")
                self.monitor_grid.add(
                    monitor.name,
                    f"{monitor.resolution} · {monitor.x}x{monitor.y} · scale {monitor.scale:g}{state}",
                )

        self.call(lambda: hyprctl("monitors", "-j", timeout=6), done)

    def _load_rules(self) -> None:
        self.call(monitor_lines, self._apply_rules)

    def _apply_rules(self, entries: list[ConfigLine]) -> None:
        while self.rules_box.count():
            item = self.rules_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._monitor_editors.clear()
        if not entries:
            self.rules_hint.setText(
                "No monitor rules found. They are usually defined in hyprland.conf."
            )
            self.save_rules_btn.setEnabled(False)
            return
        self.rules_hint.setText(
            f"{len(entries)} rules. Each rule is edited in the file where it lives; "
            "a .bak backup is written before saving."
        )
        self.save_rules_btn.setEnabled(True)
        for entry in entries:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            location = QLabel(f"{entry.path.name}:{entry.index + 1}")
            location.setObjectName("Hint")
            location.setFixedWidth(150)
            editor = QLineEdit(entry.text)
            editor.setFont(QFont(self.mono_font, 11))
            editor.setToolTip(str(entry.path))
            layout.addWidget(location)
            layout.addWidget(editor, 1)
            self.rules_box.addWidget(row)
            self._monitor_editors.append((entry, editor))

    def save_rules(self) -> None:
        changes: dict[Path, dict[int, str]] = {}
        for entry, editor in self._monitor_editors:
            value = editor.text().strip()
            if value != entry.text:
                changes.setdefault(entry.path, {})[entry.index] = value
        if not changes:
            self.notify("No monitor rules changed.", "info")
            return

        def work() -> tuple[bool, str, list[str]]:
            ok, error = update_lines(changes)
            if not ok:
                return False, error, []
            reloaded, errors = reload()
            return reloaded, "" if reloaded else "Hyprland reload failed", errors

        def done(outcome) -> None:
            ok, error, errors = outcome
            if ok:
                self.notify("Monitor rules saved and Hyprland reloaded.", "success")
            else:
                detail = "\n".join(errors[:5]) if errors else error
                self.notify(detail or "Could not reload Hyprland.", "error")
            self._load_rules()
            self.refresh_monitors()

        self.call(work, done)

    # ------------------------------------------------------------------
    def _dpms(self, on: bool) -> None:
        def done(result) -> None:
            if not result.ok:
                self.notify(result.summary(), "error")
            else:
                self.dpms_hint.setText(f"Screens turned {'on' if on else 'off'}.")

        self.call(lambda: display.dpms(on), done)

    def apply_night_light(self) -> None:
        temperature = self.night_slider.value()
        self.call(
            lambda: display.start_night_light(temperature),
            self._night_result,
        )

    def stop_night_light(self) -> None:
        self.call(
            display.stop_night_light, lambda _result: self.notify("Night light stopped.", "success")
        )

    def _night_result(self, outcome: tuple[bool, str]) -> None:
        ok, message = outcome
        self.night_hint.setText(message)
        self.notify(message, "success" if ok else "error")
