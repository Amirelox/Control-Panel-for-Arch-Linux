"""Storage page: filesystems, largest files and cleanup."""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStyle,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import storage
from ...core.commands import CommandRunner, spawn
from ...core.config import Settings
from ...core.fs import directory_size
from ...core.parsers import format_bytes
from ...core.privileged import launch_in_terminal, run_privileged
from ..widgets import BasePage, Card, DataTable


class _SizeItem(QTreeWidgetItem):
    def __lt__(self, other: QTreeWidgetItem) -> bool:
        left = self.data(0, Qt.ItemDataRole.UserRole)
        right = other.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(left, int) and isinstance(right, int):
            return left < right
        return super().__lt__(other)


class StoragePage(BasePage):
    title = "Storage"
    subtitle = "Filesystems, disk hogs and safe cleanup"
    icon_name = "drive-harddisk-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_DriveHDIcon

    scan_progress = pyqtSignal(int, str)

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
        self._scan_stop = threading.Event()
        self._scanning = False
        self.scan_progress.connect(self._on_scan_progress)

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Ghost",
            tooltip="Refresh filesystem usage",
        )

        self.add_section("Filesystems")
        self.fs_card = Card()
        self.fs_box = QVBoxLayout()
        self.fs_box.setSpacing(12)
        self.fs_card.add_layout(self.fs_box)
        self.add(self.fs_card)

        self.add_section("Largest files")
        large_card = Card("Home directory scan")
        self.scan_hint = QLabel(
            "Scan the home directory for large files. The scan is bounded and runs in the background."
        )
        self.scan_hint.setObjectName("Hint")
        self.scan_hint.setWordWrap(True)
        large_card.add(self.scan_hint)
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        self.scan_btn = QPushButton("Scan home")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.scan_home)
        self.cancel_btn = QPushButton("Cancel scan")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_scan)
        scan_row.addWidget(self.scan_btn)
        scan_row.addWidget(self.cancel_btn)
        scan_row.addStretch()
        self.scan_count = QLabel("")
        self.scan_count.setObjectName("Hint")
        scan_row.addWidget(self.scan_count)
        large_card.add_layout(scan_row)
        self.large_table = DataTable(["Size", "File"], stretch_column=1, min_height=140)
        self.large_table.set_mono_columns(0, right=True)
        self.large_table.fit_rows(empty_height=96)
        self.large_table.setSortingEnabled(True)
        self.large_table.itemDoubleClicked.connect(lambda _item, _col: self.open_selected())
        large_card.add(self.large_table)
        self.add(large_card)

        self.add_section("Maintenance")
        clean_card = Card("Cache and logs")
        self.cache_size_label = QLabel("Calculating ~/.cache size…")
        self.cache_size_label.setObjectName("Muted")
        clean_card.add(self.cache_size_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        clear_cache = QPushButton("Clear user cache")
        clear_cache.setObjectName("Danger")
        clear_cache.clicked.connect(self.clear_cache)
        pacman_cache = QPushButton("Clean pacman cache")
        pacman_cache.clicked.connect(self.clean_pacman)
        vacuum = QPushButton("Vacuum journal")
        vacuum.clicked.connect(self.vacuum_journal)
        row.addWidget(clear_cache)
        row.addWidget(pacman_cache)
        row.addWidget(vacuum)
        row.addStretch()
        clean_card.add_layout(row)
        hint = QLabel(
            "Clearing ~/.cache removes thumbnails and temporary files. Running apps may "
            "regenerate them; nothing outside your cache folder is touched."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        clean_card.add(hint)
        self.add(clean_card)
        self.add_stretch()

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def on_hide(self) -> None:
        self.cancel_scan()

    def shutdown(self) -> None:
        self._scan_stop.set()
        super().shutdown()

    def refresh(self) -> None:
        self.refresh_filesystems()
        self.refresh_cache_size()

    # ------------------------------------------------------------------
    def refresh_filesystems(self) -> None:
        self.call(storage.filesystems, self._apply_filesystems)

    def _apply_filesystems(self, entries: list[storage.FileSystem]) -> None:
        while self.fs_box.count():
            item = self.fs_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not entries:
            label = QLabel("No filesystems reported.")
            label.setObjectName("Hint")
            self.fs_box.addWidget(label)
            return
        for entry in entries:
            row = QWidget()
            layout = QVBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            head = QHBoxLayout()
            name = QLabel(
                f"<span style='font-weight:500'>{entry.mount}</span>  <span style='color:#989ba4'>{entry.device}</span>"
            )
            name.setTextFormat(Qt.TextFormat.RichText)
            info = QLabel(
                f"{format_bytes(entry.used)} / {format_bytes(entry.total)} · "
                f"{format_bytes(entry.free)} free"
            )
            info.setObjectName("MonoHint")
            head.addWidget(name)
            head.addStretch()
            head.addWidget(info)
            layout.addLayout(head)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(entry.percent))
            bar.setTextVisible(False)
            bar.setFixedHeight(9)
            if entry.percent >= 90:
                bar.setStyleSheet("QProgressBar::chunk { background: #d97b7b; }")
            elif entry.percent >= 75:
                bar.setStyleSheet("QProgressBar::chunk { background: #d6a45f; }")
            layout.addWidget(bar)
            self.fs_box.addWidget(row)

    # ------------------------------------------------------------------
    def scan_home(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._scan_stop.clear()
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning…")
        self.cancel_btn.setEnabled(True)
        self.scan_count.setText("Starting scan…")
        self.large_table.clear()

        def progress(count: int, path: str) -> None:
            self.scan_progress.emit(count, path)

        def work():
            return storage.scan_large_files(
                Path.home(),
                limit=40,
                max_files=self.settings.scan_limit,
                progress=progress,
                should_stop=self._scan_stop.is_set,
            )

        def done(result) -> None:
            entries, scanned, truncated = result
            self._scanning = False
            self.scan_btn.setEnabled(True)
            self.scan_btn.setText("Scan home")
            self.cancel_btn.setEnabled(False)
            self.large_table.setSortingEnabled(False)
            self.large_table.clear()
            self.large_table.fit_rows(empty_height=96)
            for size, path in entries:
                item = _SizeItem([format_bytes(size), str(path)])
                item.setData(0, Qt.ItemDataRole.UserRole, size)
                item.setData(1, Qt.ItemDataRole.UserRole, str(path))
                self.large_table.addTopLevelItem(item)
            self.large_table.setSortingEnabled(True)
            self.large_table.fit_rows(max_rows=10, empty_height=96)
            note = f"Scanned {scanned:,} files."
            if truncated:
                note += " Result limit reached."
            if self._scan_stop.is_set():
                note += " Scan cancelled."
            self.scan_count.setText(note)

        def failed(message: str, _trace: str) -> None:
            self._scanning = False
            self.scan_btn.setEnabled(True)
            self.scan_btn.setText("Scan home")
            self.cancel_btn.setEnabled(False)
            self.notify(message, "error")

        self.runner.submit(work, on_done=done, on_error=failed)

    def _on_scan_progress(self, count: int, path: str) -> None:
        self.scan_count.setText(f"Scanned {count:,} files… {path}")

    def cancel_scan(self) -> None:
        if self._scanning:
            self._scan_stop.set()
            self.cancel_btn.setEnabled(False)
            self.scan_count.setText("Cancelling scan…")

    def open_selected(self) -> None:
        item = self.large_table.currentItem()
        if item is None:
            return
        path = item.data(1, Qt.ItemDataRole.UserRole)
        if not path:
            return
        spawn(["xdg-open", str(Path(path).parent)])

    # ------------------------------------------------------------------
    def refresh_cache_size(self) -> None:
        self.cache_size_label.setText("Calculating ~/.cache size…")

        def work():
            cache = storage.user_cache()
            return cache, directory_size(cache)

        def done(result) -> None:
            cache, size = result
            self.cache_size_label.setText(f"{cache} · {format_bytes(size)}")

        self.call(work, done)

    def clear_cache(self) -> None:
        cache = storage.user_cache()
        if not self.confirm(
            "Clear user cache",
            f"Delete the contents of {cache}?\n\n"
            "Thumbnails and temporary files will be removed. This cannot be undone.",
            danger=True,
            ok_text="Clear cache",
        ):
            return

        def done(result: tuple[int, int]) -> None:
            files, size = result
            self.notify(f"Removed {files:,} files ({format_bytes(size)}).", "success")
            self.refresh_cache_size()

        self.call(storage.clear_user_cache, done)

    def clean_pacman(self) -> None:
        if not self.confirm(
            "Clean pacman cache",
            "Remove old package files with paccache?\n\nThe command runs in a terminal window.",
            ok_text="Open terminal",
        ):
            return
        ok, error = launch_in_terminal(
            ["sudo", "paccache", "-r"],
            title="Clean pacman cache",
            terminal=self.settings.terminal,
        )
        self.notify("Cleanup window opened." if ok else error, "success" if ok else "error")

    def vacuum_journal(self) -> None:
        if not self.confirm(
            "Vacuum journal",
            "Reduce the systemd journal to 200 MiB?\n\nThis requires administrator rights.",
            ok_text="Vacuum",
        ):
            return

        def work():
            return run_privileged(
                ["journalctl", "--vacuum-size=200M"],
                timeout=60,
            )

        def done(result) -> None:
            if result.ok:
                self.notify(result.output or "Journal vacuumed.", "success")
            else:
                self.notify(result.summary(), "error")

        self.call(work, done)
