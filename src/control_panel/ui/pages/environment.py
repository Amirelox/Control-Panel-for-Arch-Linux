"""Environment page: variables, Hyprland env and shell configuration."""

from __future__ import annotations

import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QTabWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.commands import CommandRunner
from ...core.config import Settings, home, modules_dir
from ...core.fs import read_text, write_text_atomic
from ...core.hyprland import reload
from ...core.parsers import mask_secret
from ..widgets import BasePage, Card, CodeEditor, DataTable, SearchField


class EnvironmentPage(BasePage):
    title = "Environment"
    subtitle = "Process environment, Hyprland variables and shell startup"
    icon_name = "utilities-terminal-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_ComputerIcon

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
        self._env: dict[str, str] = {}
        self._shell_rc = home() / ".zshrc" if (home() / ".zshrc").exists() else home() / ".bashrc"
        self._sensitive = re.compile(r"KEY|TOKEN|SECRET|PASS|API|AUTH|COOKIE|CREDENTIAL", re.I)

        self.add_action_button(
            "Copy variable",
            self.copy_selected,
            icon="edit-copy",
            style="Ghost",
            tooltip="Copy the selected environment value",
        )

        tabs = QTabWidget()
        tabs.addTab(self._build_env_tab(), "Variables")
        tabs.addTab(self._build_hypr_env_tab(), "Hyprland env")
        tabs.addTab(self._build_shell_tab(), "Shell")
        tabs.addTab(self._build_path_tab(), "PATH")
        tabs.setMinimumHeight(420)
        self.add(tabs, 1)

    # ------------------------------------------------------------------
    def _build_env_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.env_search = SearchField("Filter variables…")
        self.env_search.textChanged.connect(self._filter_env)
        self.show_sensitive = QCheckBox("Show sensitive values")
        self.show_sensitive.setChecked(not self.settings.hide_sensitive_env)
        self.show_sensitive.toggled.connect(lambda _checked: self._populate_env())
        row.addWidget(self.env_search, 1)
        row.addWidget(self.show_sensitive)
        layout.addLayout(row)

        self.env_table = DataTable(["Variable", "Value"], stretch_column=1, min_height=300)
        self.env_table.setSortingEnabled(True)
        layout.addWidget(self.env_table, 1)
        hint = QLabel("Values whose names look like secrets are masked by default.")
        hint.setObjectName("Hint")
        layout.addWidget(hint)
        return page

    def _build_hypr_env_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(8)
        path = modules_dir() / "env.conf"
        self.hypr_env_path = path
        self.hypr_env_editor = CodeEditor(mono_font=self.mono_font)
        self.hypr_env_editor.setPlainText(read_text(path))
        layout.addWidget(self.hypr_env_editor, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        save = QPushButton("Save and reload Hyprland")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_hypr_env)
        row.addWidget(save)
        row.addWidget(QLabel(str(path)))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _build_shell_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(8)
        self.shell_editor = CodeEditor(mono_font=self.mono_font)
        self.shell_editor.setPlainText(read_text(self._shell_rc))
        layout.addWidget(self.shell_editor, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        save = QPushButton(f"Save {self._shell_rc.name}")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_shell)
        row.addWidget(save)
        row.addWidget(QLabel(str(self._shell_rc)))
        row.addStretch()
        layout.addLayout(row)
        return page

    def _build_path_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(10)
        card = Card("PATH entries")
        self.path_table = DataTable(
            ["Directory", "Exists", "Executables"],
            stretch_column=0,
            min_height=260,
        )
        card.add(self.path_table)
        self.path_hint = QLabel("")
        self.path_hint.setObjectName("Hint")
        card.add(self.path_hint)
        layout.addWidget(card)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._env = dict(os.environ)
        self._populate_env()
        self._populate_path()

    def _filter_env(self, text: str) -> None:
        query = text.strip().lower()
        for index in range(self.env_table.topLevelItemCount()):
            item = self.env_table.topLevelItem(index)
            item.setHidden(bool(query) and query not in item.text(0).lower())

    def _populate_env(self) -> None:
        show = self.show_sensitive.isChecked()
        self.env_table.setSortingEnabled(False)
        self.env_table.clear()
        for key, value in sorted(self._env.items()):
            display = value
            if not show and self._sensitive.search(key):
                display = mask_secret(value)
            item = QTreeWidgetItem([key, display])
            item.setData(1, Qt.ItemDataRole.UserRole, value)
            item.setToolTip(1, "Sensitive value masked" if display != value else value)
            self.env_table.addTopLevelItem(item)
        self.env_table.setSortingEnabled(True)
        self._filter_env(self.env_search.text())

    def copy_selected(self) -> None:
        item = self.env_table.currentItem()
        if item is None:
            self.notify("Select a variable first.", "info")
            return
        value = item.data(1, Qt.ItemDataRole.UserRole)
        from PyQt6.QtWidgets import QApplication

        QApplication.clipboard().setText(str(value))
        self.notify(f"{item.text(0)} copied to the clipboard.", "success")

    def _populate_path(self) -> None:
        self.path_table.clear_rows()
        entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
        for entry in entries:
            path = Path(entry)
            exists = path.is_dir()
            count = 0
            if exists:
                try:
                    count = sum(
                        1
                        for child in path.iterdir()
                        if child.is_file() and os.access(child, os.X_OK)
                    )
                except OSError:
                    count = 0
            self.path_table.addTopLevelItem(
                QTreeWidgetItem([entry, "Yes" if exists else "No", f"{count:,}"])
            )
        self.path_hint.setText(
            f"{len(entries)} PATH entries · {sum(1 for entry in entries if Path(entry).is_dir())} exist"
        )

    # ------------------------------------------------------------------
    def save_hypr_env(self) -> None:
        try:
            write_text_atomic(self.hypr_env_path, self.hypr_env_editor.toPlainText(), backup=True)
        except OSError as exc:
            self.notify(str(exc), "error")
            return

        def done(result) -> None:
            ok, errors = result
            if ok:
                self.notify("env.conf saved and Hyprland reloaded.", "success")
            else:
                self.notify("\n".join(errors[:4]) or "Hyprland reload failed.", "error")

        self.call(reload, done)

    def save_shell(self) -> None:
        try:
            write_text_atomic(self._shell_rc, self.shell_editor.toPlainText(), backup=True)
        except OSError as exc:
            self.notify(str(exc), "error")
            return
        self.notify(f"{self._shell_rc.name} saved. Open a new shell to apply it.", "success")
