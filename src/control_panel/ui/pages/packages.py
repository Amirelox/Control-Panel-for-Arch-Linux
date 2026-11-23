"""Packages page: search, install, remove and system updates."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTreeWidgetItem,
)

from ...core import packages
from ...core.commands import CommandRunner
from ...core.config import Settings
from ...core.parsers import Package
from ..widgets import BasePage, Card, DataTable, SearchField, ask


class PackagesPage(BasePage):
    title = "Packages"
    subtitle = "Search pacman/AUR and keep the system up to date"
    icon_name = "package-x-generic-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_DirIcon

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
        self._results: list[Package] = []
        self._busy = False

        self.add_action_button(
            "Check updates",
            self.refresh_updates,
            icon="view-refresh",
            style="Ghost",
            tooltip="Check for available package updates",
        )

        self.add_section("Search")
        search_card = Card()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.search_field = SearchField("Search packages")
        self.search_field.returnPressed.connect(self.run_search)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Official + AUR", "Official", "AUR"])
        search_btn = QPushButton("Search")
        search_btn.setObjectName("Primary")
        search_btn.clicked.connect(self.run_search)
        self.search_btn = search_btn
        row.addWidget(self.search_field, 1)
        row.addWidget(self.source_combo)
        row.addWidget(search_btn)
        search_card.add_layout(row)
        self.search_hint = QLabel("Search official repositories or AUR.")
        self.search_hint.setObjectName("Hint")
        search_card.add(self.search_hint)
        self.add(search_card)

        self.add_section("Results")
        results_card = Card()
        self.table = DataTable(
            ["Package", "Version", "Source", "Installed", "Description"],
            stretch_column=4,
            min_height=160,
        )
        self.table.set_mono_columns(1, right=False)
        self.table.fit_rows(empty_height=96)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        results_card.add(self.table)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.install_btn = QPushButton("Install selected")
        self.install_btn.setObjectName("Success")
        self.install_btn.clicked.connect(self.install_selected)
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.setObjectName("Danger")
        self.remove_btn.clicked.connect(self.remove_selected)
        buttons.addWidget(self.install_btn)
        buttons.addWidget(self.remove_btn)
        buttons.addStretch()
        self.selected_hint = QLabel("")
        self.selected_hint.setObjectName("Hint")
        buttons.addWidget(self.selected_hint)
        results_card.add_layout(buttons)
        self.add(results_card)

        self.add_section("System update")
        update_card = Card()
        self.update_summary = QLabel("Checking for updates…")
        self.update_summary.setObjectName("Muted")
        update_card.add(self.update_summary)
        self.update_list = QPlainTextEdit()
        self.update_list.setReadOnly(True)
        self.update_list.setMaximumHeight(110)
        self.update_list.setPlaceholderText("No updates pending.")
        self.update_list.setFont(QFont(self.mono_font, 10))
        update_card.add(self.update_list)
        update_row = QHBoxLayout()
        update_row.setSpacing(8)
        check_btn = QPushButton("Check now")
        check_btn.clicked.connect(self.refresh_updates)
        self.upgrade_btn = QPushButton("Upgrade system")
        self.upgrade_btn.setObjectName("Primary")
        self.upgrade_btn.clicked.connect(self.upgrade)
        update_row.addWidget(check_btn)
        update_row.addWidget(self.upgrade_btn)
        update_row.addStretch()
        update_card.add_layout(update_row)
        self.add(update_card)
        self.add_stretch()

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh_updates()

    def refresh(self) -> None:
        self.refresh_updates()

    # ------------------------------------------------------------------
    def run_search(self) -> None:
        query = self.search_field.text().strip()
        if not query:
            self.notify("Type a package name or keyword.", "info")
            return
        if self._busy:
            return
        self._busy = True
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching…")
        self.search_hint.setText("Searching…")
        mode = self.source_combo.currentIndex()

        def work():
            if mode == 0:
                return packages.search_both(query)
            if mode == 2:
                return packages.search(query, aur=True)
            return packages.search(query, aur=False)

        def done(result: packages.SearchResult) -> None:
            self._busy = False
            self.search_btn.setEnabled(True)
            self.search_btn.setText("Search")
            self._results = result.packages
            self._populate_results()
            self.search_hint.setText(
                f"{len(result.packages)} result(s)." + (f" {result.error}" if result.error else "")
            )

        def failed(message: str, _trace: str) -> None:
            self._busy = False
            self.search_btn.setEnabled(True)
            self.search_btn.setText("Search")
            self.notify(message, "error")

        self.runner.submit(work, on_done=done, on_error=failed)

    def _populate_results(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.clear()
        for package in self._results:
            item = QTreeWidgetItem(
                [
                    package.name,
                    package.version,
                    package.source,
                    "Yes" if package.installed else "",
                    package.description,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, package)
            self.table.addTopLevelItem(item)
        self.table.setSortingEnabled(True)
        self.table.fit_rows(max_rows=10, empty_height=96)
        self.install_btn.setEnabled(bool(self._results))
        self._selection_changed()

    def _selected_package(self) -> Package | None:
        item = self.table.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return data if isinstance(data, Package) else None

    def _selection_changed(self) -> None:
        package = self._selected_package()
        if package is None:
            self.selected_hint.setText("")
            self.remove_btn.setEnabled(False)
            return
        self.selected_hint.setText(f"{package.name} · {package.source} · {package.version}")
        self.remove_btn.setEnabled(package.installed)

    def install_selected(self) -> None:
        package = self._selected_package()
        if package is None:
            self.notify("Select a package first.", "info")
            return
        aur = package.repo.lower() == "aur"
        if not ask(
            self,
            "Install package",
            f"Install “{package.name}” {package.version} from {package.source}?\n\n"
            "The package manager opens in a terminal window.",
            ok_text="Install",
        ):
            return
        ok, error = packages.install([package.name], aur=aur, terminal=self.settings.terminal)
        if ok:
            self.notify(f"Installation window opened for {package.name}.", "success")
        else:
            self.notify(error, "error")

    def remove_selected(self) -> None:
        package = self._selected_package()
        if package is None:
            self.notify("Select a package first.", "info")
            return
        if not ask(
            self,
            "Remove package",
            f"Remove “{package.name}” and its unused dependencies?\n\n"
            "The package manager opens in a terminal window.",
            danger=True,
            ok_text="Remove",
        ):
            return
        ok, error = packages.remove([package.name], terminal=self.settings.terminal)
        if ok:
            self.notify(f"Removal window opened for {package.name}.", "success")
        else:
            self.notify(error, "error")

    # ------------------------------------------------------------------
    def refresh_updates(self) -> None:
        self.update_summary.setText("Checking for updates…")
        self.upgrade_btn.setEnabled(False)

        def done(result: tuple[list, str]) -> None:
            entries, error = result
            self.upgrade_btn.setEnabled(bool(entries))
            if error:
                self.update_summary.setText(f"Could not check updates: {error}")
                self.update_list.setPlainText("")
                return
            if not entries:
                self.update_summary.setText("System is up to date.")
                self.update_list.setPlainText("")
                return
            self.update_summary.setText(f"{len(entries)} updates available")
            self.update_list.setPlainText(
                "\n".join(
                    f"{entry.name}  {entry.old_version} → {entry.new_version}" for entry in entries
                )
            )

        self.call(packages.updates, done)

    def upgrade(self) -> None:
        if not ask(
            self,
            "Upgrade system",
            "Run a full system upgrade (yay -Syu)?\n\n"
            "The upgrade runs in a terminal window so you can see progress.",
            ok_text="Upgrade",
        ):
            return
        ok, error = packages.upgrade(terminal=self.settings.terminal)
        if ok:
            self.notify("Upgrade window opened.", "success")
        else:
            self.notify(error, "error")
