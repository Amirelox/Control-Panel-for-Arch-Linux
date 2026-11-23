"""Processes page: process list and systemd services."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QTabWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import processes
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.parsers import format_bytes
from ..widgets import BasePage, DataTable, SearchField, ask


class _NumericItem(QTreeWidgetItem):
    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        left = self.data(column, Qt.ItemDataRole.UserRole)
        right = other.data(column, Qt.ItemDataRole.UserRole)
        if left is not None and right is not None:
            try:
                return float(left) < float(right)
            except (TypeError, ValueError):
                pass
        return self.text(column) < other.text(column)


class ProcessesPage(BasePage):
    title = "Processes"
    subtitle = "Running processes and systemd services"
    icon_name = "view-process-all-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_BrowserReload

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
        self._processes: list[processes.ProcessInfo] = []
        self._services: list[processes.ServiceInfo] = []
        self._busy = False
        self._svc_busy = False
        self._process_timer = QTimer(self)
        self._process_timer.setInterval(3000)
        self._process_timer.timeout.connect(self.refresh_processes)

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Primary",
            tooltip="Refresh processes and services",
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_process_tab(), "Processes")
        self.tabs.addTab(self._build_services_tab(), "Services")
        self.tabs.setMinimumHeight(460)
        self.add(self.tabs, 1)

    # ------------------------------------------------------------------
    def _build_process_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.process_search = SearchField("Filter processes…")
        self.process_search.textChanged.connect(self._apply_process_filter)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.refresh_processes)
        row.addWidget(self.process_search, 1)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.process_table = DataTable(
            ["PID", "Name", "User", "CPU %", "MEM %", "Memory", "Status"],
            stretch_column=1,
            min_height=280,
        )
        self.process_table.setSortingEnabled(True)
        self.process_table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.process_table.itemDoubleClicked.connect(
            lambda _item, _col: self.kill_process(force=False)
        )
        layout.addWidget(self.process_table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        terminate = QPushButton("Terminate selected")
        terminate.clicked.connect(lambda: self.kill_process(force=False))
        force = QPushButton("Force kill")
        force.setObjectName("Danger")
        force.clicked.connect(lambda: self.kill_process(force=True))
        actions.addWidget(terminate)
        actions.addWidget(force)
        actions.addStretch()
        self.process_hint = QLabel("")
        self.process_hint.setObjectName("Hint")
        actions.addWidget(self.process_hint)
        layout.addLayout(actions)
        return page

    def _build_services_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["System", "User"])
        self.scope_combo.currentIndexChanged.connect(lambda _index: self.refresh_services())
        self.service_search = SearchField("Filter services…")
        self.service_search.textChanged.connect(self._apply_service_filter)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.refresh_services)
        row.addWidget(QLabel("Scope"))
        row.addWidget(self.scope_combo)
        row.addWidget(self.service_search, 1)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.service_table = DataTable(
            ["Unit", "Load", "Active", "Sub", "Description"],
            stretch_column=4,
            min_height=260,
        )
        self.service_table.setSortingEnabled(True)
        layout.addWidget(self.service_table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        for label, verb, style in (
            ("Start", "start", ""),
            ("Stop", "stop", ""),
            ("Restart", "restart", ""),
            ("Enable", "enable", ""),
            ("Disable", "disable", ""),
        ):
            button = QPushButton(label)
            if style:
                button.setObjectName(style)
            button.clicked.connect(lambda _checked=False, v=verb: self.service_action(v))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        hint = QLabel("System services use polkit (pkexec) when administrator rights are required.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return page

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._process_timer.start()
        if not self._processes:
            self.refresh_processes()
            QTimer.singleShot(900, self.refresh_processes)
        if not self._services:
            self.refresh_services()

    def on_hide(self) -> None:
        self._process_timer.stop()

    def refresh(self) -> None:
        self.refresh_processes()
        self.refresh_services()

    # ------------------------------------------------------------------
    def refresh_processes(self) -> None:
        if self._busy:
            return
        self._busy = True

        def done(items: list[processes.ProcessInfo]) -> None:
            self._busy = False
            self._processes = items
            self._apply_process_filter(self.process_search.text())
            self.process_hint.setText(f"{len(items)} processes · updates every 3 s")

        def failed(message: str, _trace: str) -> None:
            self._busy = False
            self.notify(message, "error")

        self.runner.submit(processes.process_snapshot, on_done=done, on_error=failed)

    def _apply_process_filter(self, text: str) -> None:
        query = text.strip().lower()
        self.process_table.setSortingEnabled(False)
        self.process_table.clear()
        for entry in self._processes:
            if (
                query
                and query not in entry.name.lower()
                and query not in entry.user.lower()
                and query not in entry.command.lower()
            ):
                continue
            item = _NumericItem(
                [
                    str(entry.pid),
                    entry.name,
                    entry.user,
                    f"{entry.cpu:.1f}",
                    f"{entry.memory:.1f}",
                    format_bytes(entry.rss),
                    entry.status,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry.pid)
            item.setData(3, Qt.ItemDataRole.UserRole, entry.cpu)
            item.setData(4, Qt.ItemDataRole.UserRole, entry.memory)
            item.setData(5, Qt.ItemDataRole.UserRole, entry.rss)
            item.setToolTip(1, entry.command or entry.name)
            self.process_table.addTopLevelItem(item)
        self.process_table.setSortingEnabled(True)

    def kill_process(self, *, force: bool) -> None:
        item = self.process_table.currentItem()
        if item is None:
            self.notify("Select a process first.", "info")
            return
        pid = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(pid, int):
            return
        name = item.text(1)
        verb = "force kill" if force else "terminate"
        if not ask(
            self,
            "Stop process",
            f"{verb.capitalize()} “{name}” (PID {pid})?",
            danger=force,
            ok_text="Force kill" if force else "Terminate",
        ):
            return

        def done(outcome: tuple[bool, str]) -> None:
            ok, message = outcome
            self.notify(message, "success" if ok else "error")
            self.refresh_processes()

        self.call(lambda: processes.kill_process(pid, force=force), done)

    # ------------------------------------------------------------------
    def refresh_services(self) -> None:
        if self._svc_busy:
            return
        self._svc_busy = True
        user = self.scope_combo.currentIndex() == 1

        def done(items: list[processes.ServiceInfo]) -> None:
            self._svc_busy = False
            self._services = items
            self._apply_service_filter(self.service_search.text())
            if not items:
                self.notify("No services returned. Is systemd available?", "warning")

        def failed(message: str, _trace: str) -> None:
            self._svc_busy = False
            self.notify(message, "error")

        self.runner.submit(lambda: processes.services(user=user), on_done=done, on_error=failed)

    def _apply_service_filter(self, text: str) -> None:
        query = text.strip().lower()
        self.service_table.setSortingEnabled(False)
        self.service_table.clear()
        for entry in self._services:
            if query and query not in entry.unit.lower() and query not in entry.description.lower():
                continue
            item = QTreeWidgetItem(
                [entry.unit, entry.load, entry.active, entry.sub, entry.description]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry.unit)
            self.service_table.addTopLevelItem(item)
        self.service_table.setSortingEnabled(True)

    def service_action(self, verb: str) -> None:
        item = self.service_table.currentItem()
        if item is None:
            self.notify("Select a service first.", "info")
            return
        unit = item.text(0)
        user = self.scope_combo.currentIndex() == 1
        if verb in {"stop", "disable"} and not self.confirm(
            f"{verb.capitalize()} service",
            f"{verb.capitalize()} {unit}?",
            danger=False,
            ok_text=verb.capitalize(),
        ):
            return

        def done(result) -> None:
            self.notify(
                f"{unit}: {verb} requested." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )
            self.refresh_services()

        self.call(lambda: processes.service_action(unit, verb, user=user), done)
