"""Hyprland page: config editors and live tweaks."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import hyprland
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.fs import read_text, write_text_atomic
from ...core.parsers import parse_config_errors
from ..widgets import BasePage, Card, CodeEditor


class _EditorTab(QWidget):
    def __init__(self, path: Path, text: str, *, mono_font: str, page: HyprlandPage) -> None:
        super().__init__()
        self.path = path
        self.page = page
        self.dirty = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        self.editor = CodeEditor(mono_font=mono_font)
        self.editor.setPlainText(text)
        self.editor.textChanged.connect(self._mark_dirty)
        layout.addWidget(self.editor, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_label = QLabel(str(path))
        self.path_label.setObjectName("Hint")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.save_btn = QPushButton("Save and reload")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(lambda: page.save_tab(self))
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.setObjectName("Ghost")
        self.revert_btn.clicked.connect(lambda: page.revert_tab(self))
        row.addWidget(self.save_btn)
        row.addWidget(self.revert_btn)
        row.addWidget(self.path_label, 1)
        layout.addLayout(row)

    def _mark_dirty(self) -> None:
        self.dirty = True
        self.page.mark_dirty(self)

    def load(self) -> None:
        self.editor.blockSignals(True)
        self.editor.setPlainText(read_text(self.path))
        self.editor.blockSignals(False)
        self.dirty = False
        self.page.mark_clean(self)


class HyprlandPage(BasePage):
    title = "Hyprland"
    subtitle = "Edit configuration modules and tune the compositor live"
    icon_name = "preferences-system-windows-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_TitleBarMaxButton

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
        self._tabs_by_path: dict[Path, _EditorTab] = {}
        self._option_widgets: dict[str, tuple[QSlider | QCheckBox, QLabel | None]] = {}
        self._option_timers: dict[str, QTimer] = {}
        self._options_loaded = False

        self.add_action_button(
            "Reload",
            self.reload_hyprland,
            icon="view-refresh",
            style="Ghost",
            tooltip="Run hyprctl reload",
        )
        self.add_action_button(
            "Errors",
            self.show_errors,
            icon="dialog-warning",
            style="Ghost",
            tooltip="Show Hyprland configuration errors",
        )

        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(420)
        self.add(self.tabs, 1)
        shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        shortcut.activated.connect(self.save_current)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self._build_tabs()

    def _build_tabs(self) -> None:
        def work():
            files = hyprland.config_files()
            return [(path, read_text(path)) for path in files if path.name != "colors.conf"]

        def done(files) -> None:
            self.tabs.clear()
            self._tabs_by_path.clear()
            if not files:
                self.tabs.addTab(QWidget(), "No config")
                self.tabs.setToolTip(
                    f"Could not find Hyprland configuration at {hyprland_config_hint()}"
                )
                self.add_tweaks_tab()
                return
            for path, text in files:
                tab = _EditorTab(path, text, mono_font=self.mono_font, page=self)
                self._tabs_by_path[path] = tab
                self.tabs.addTab(tab, path.name)
                self.tabs.setTabToolTip(self.tabs.indexOf(tab), str(path))
            self.add_tweaks_tab()

        self.call(work, done)

    def add_tweaks_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(12)
        hint = QLabel(
            "These controls change Hyprland live with hyprctl keyword. "
            "They are not written to disk — use the config tabs for permanent changes."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        card = Card("Live values")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        specs = [
            ("decoration:rounding", "Corner rounding", 0, 30, "int"),
            ("general:gaps_in", "Gaps in", 0, 40, "int"),
            ("general:gaps_out", "Gaps out", 0, 60, "int"),
            ("decoration:active_opacity", "Window opacity", 50, 100, "opacity"),
            ("decoration:blur:size", "Blur size", 0, 24, "int"),
        ]
        for row, (key, label, low, high, kind) in enumerate(specs):
            name = QLabel(label)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            value_label = QLabel("—")
            value_label.setMinimumWidth(46)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            slider.valueChanged.connect(
                lambda value, k=key, vl=value_label, kd=kind: self._option_changed(k, value, vl, kd)
            )
            grid.addWidget(name, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value_label, row, 2)
            self._option_widgets[key] = (slider, value_label)
        card.add_layout(grid)

        blur = QCheckBox("Enable blur")
        blur.toggled.connect(
            lambda enabled: self._toggle_option("decoration:blur:enabled", enabled)
        )
        card.add(blur)
        self._option_widgets["decoration:blur:enabled"] = (blur, None)

        layout.addWidget(card)
        layout.addStretch()
        self.tabs.addTab(widget, "Live tweaks")
        self._load_options()

    def _load_options(self) -> None:
        if self._options_loaded:
            return

        def work():
            values = {}
            for key in self._option_widgets:
                values[key] = hyprland.get_option(key)
            return values

        def done(values) -> None:
            self._options_loaded = True
            for key, value in values.items():
                widget, label = self._option_widgets[key]
                if value is None:
                    widget.setEnabled(False)
                    if label is not None:
                        label.setText("n/a")
                    continue
                if isinstance(widget, QCheckBox):
                    widget.blockSignals(True)
                    if isinstance(value, str):
                        widget.setChecked(value.lower() in {"true", "1", "yes", "on"})
                    else:
                        widget.setChecked(bool(value))
                    widget.blockSignals(False)
                    continue
                try:
                    ivalue = float(str(value).split()[0])
                except (TypeError, ValueError, IndexError):
                    widget.setEnabled(False)
                    if label is not None:
                        label.setText("n/a")
                    continue
                if key.endswith("active_opacity") and ivalue <= 1.0:
                    ivalue *= 100
                widget.blockSignals(True)
                widget.setValue(round(ivalue))
                widget.blockSignals(False)
                if label is not None:
                    self._set_option_text(key, label, widget.value())

        self.call(work, done)

    def _option_changed(self, key: str, value: int, label: QLabel, kind: str) -> None:
        self._set_option_text(key, label, value)
        timer = self._option_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(250)
            timer.timeout.connect(lambda k=key: self._apply_option(k))
            self._option_timers[key] = timer
        timer.start()

    @staticmethod
    def _set_option_text(key: str, label: QLabel, value: int) -> None:
        if key.endswith("active_opacity"):
            label.setText(f"{value}%")
        else:
            label.setText(str(value))

    def _apply_option(self, key: str) -> None:
        widget, _label = self._option_widgets[key]
        if isinstance(widget, QCheckBox):
            value = "true" if widget.isChecked() else "false"
        else:
            value = str(widget.value())
            if key.endswith("active_opacity"):
                value = f"{widget.value() / 100:.2f}"
        self.call(
            lambda: hyprland.hyprctl("keyword", key, value, timeout=5),
            lambda result: None if result.ok else self.notify(result.summary(), "error"),
        )

    def _toggle_option(self, key: str, enabled: bool) -> None:
        self.call(
            lambda: hyprland.hyprctl("keyword", key, "true" if enabled else "false", timeout=5),
            lambda result: None if result.ok else self.notify(result.summary(), "error"),
        )

    # ------------------------------------------------------------------
    def mark_dirty(self, tab: _EditorTab) -> None:
        index = self.tabs.indexOf(tab)
        if index >= 0 and not self.tabs.tabText(index).endswith(" *"):
            self.tabs.setTabText(index, self.tabs.tabText(index) + " *")

    def mark_clean(self, tab: _EditorTab) -> None:
        index = self.tabs.indexOf(tab)
        if index >= 0:
            self.tabs.setTabText(index, self.tabs.tabText(index).removesuffix(" *"))

    def save_current(self) -> None:
        current = self.tabs.currentWidget()
        if isinstance(current, _EditorTab):
            self.save_tab(current)

    def save_tab(self, tab: _EditorTab) -> None:
        text = tab.editor.toPlainText()
        try:
            write_text_atomic(tab.path, text, backup=True)
        except OSError as exc:
            self.notify(f"Could not save {tab.path.name}: {exc}", "error")
            return
        tab.dirty = False
        self.mark_clean(tab)
        self.notify(f"Saved {tab.path.name}.", "success")
        self._reload_with_errors()

    def revert_tab(self, tab: _EditorTab) -> None:
        if tab.dirty and not self.confirm(
            "Revert file",
            f"Discard unsaved changes in {tab.path.name}?",
            danger=True,
            ok_text="Discard",
        ):
            return
        tab.load()

    def reload_hyprland(self) -> None:
        self._reload_with_errors()

    def _reload_with_errors(self) -> None:
        def done(result: tuple[bool, list[str]]) -> None:
            ok, errors = result
            if ok:
                self.notify("Hyprland reloaded without errors.", "success")
            else:
                message = "\n".join(errors[:4]) if errors else "Hyprland reload failed."
                self.notify(message, "error")

        self.call(hyprland.reload, done)

    def show_errors(self) -> None:
        def done(result) -> None:
            if not result.ok:
                self.notify(result.summary(), "error")
                return
            errors = parse_config_errors(result.stdout)
            self.notify(
                "\n".join(errors[:6]) if errors else "No configuration errors.",
                "warning" if errors else "success",
                timeout_ms=7000,
            )

        self.call(lambda: hyprland.hyprctl("configerrors", "-j", timeout=6), done)


def hyprland_config_hint() -> str:
    from ...core.config import hyprland_conf

    return str(hyprland_conf())
