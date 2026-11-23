"""Preferences dialog."""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..core.config import Settings, home
from ..core.privileged import TERMINALS, terminal_available


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(480)
        self._original = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.refresh_combo = QComboBox()
        for label, value in (
            ("0.5 seconds", 500),
            ("1 second", 1000),
            ("2 seconds", 2000),
            ("5 seconds", 5000),
        ):
            self.refresh_combo.addItem(label, value)
        self._select(self.refresh_combo, settings.refresh_ms)
        form.addRow("Refresh interval", self.refresh_combo)

        self.accent_combo = QComboBox()
        for label, value in (
            ("Follow Hyprland colours", "auto"),
            ("Violet", "violet"),
            ("Green", "green"),
            ("Blue", "blue"),
            ("Rose", "rose"),
        ):
            self.accent_combo.addItem(label, value)
        index = self.accent_combo.findData(settings.accent)
        self.accent_combo.setCurrentIndex(max(0, index))
        form.addRow("Accent", self.accent_combo)

        self.terminal_combo = QComboBox()
        self.terminal_combo.addItem("Auto-detect", "")
        for name in TERMINALS:
            if terminal_available(name):
                self.terminal_combo.addItem(name, name)
        index = self.terminal_combo.findData(settings.terminal)
        self.terminal_combo.setCurrentIndex(max(0, index))
        form.addRow("Terminal", self.terminal_combo)

        self.confirm_check = QCheckBox("Ask before destructive actions")
        self.confirm_check.setChecked(settings.confirm_destructive)
        form.addRow("", self.confirm_check)

        self.sensitive_check = QCheckBox("Mask secret environment variables")
        self.sensitive_check.setChecked(settings.hide_sensitive_env)
        form.addRow("", self.sensitive_check)

        self.scan_spin = QSpinBox()
        self.scan_spin.setRange(10_000, 2_000_000)
        self.scan_spin.setSingleStep(50_000)
        self.scan_spin.setSuffix(" files")
        self.scan_spin.setValue(settings.scan_limit)
        form.addRow("Large-file scan limit", self.scan_spin)

        self.wallpaper_edit = QPlainTextEdit()
        self.wallpaper_edit.setMinimumHeight(90)
        self.wallpaper_edit.setPlainText("\n".join(settings.wallpaper_dirs))
        form.addRow("Wallpaper folders", self.wallpaper_edit)
        layout.addLayout(form)

        hint = QLabel(
            f"Settings are stored in {home() / '.config' / 'control-panel' / 'settings.json'}"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _select(combo: QComboBox, value: int) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def result_settings(self) -> Settings:
        wallpaper_dirs = [
            line.strip() for line in self.wallpaper_edit.toPlainText().splitlines() if line.strip()
        ]
        return replace(
            self._original,
            refresh_ms=int(self.refresh_combo.currentData()),
            accent=str(self.accent_combo.currentData()),
            terminal=str(self.terminal_combo.currentData()),
            confirm_destructive=self.confirm_check.isChecked(),
            hide_sensitive_env=self.sensitive_check.isChecked(),
            scan_limit=self.scan_spin.value(),
            wallpaper_dirs=wallpaper_dirs,
        )
