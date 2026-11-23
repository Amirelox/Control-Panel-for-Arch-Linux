"""Main window, navigation and global status footer."""

from __future__ import annotations

import contextlib
import dataclasses
import os
import traceback
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QByteArray, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__
from ..core.commands import CommandRunner
from ..core.config import Settings, SettingsStore
from ..core.parsers import format_rate
from ..core.privileged import is_hyprland
from ..core.stats import Stats, StatsWorker
from .pages.appearance import AppearancePage
from .pages.audio import AudioPage
from .pages.bluetooth import BluetoothPage
from .pages.display import DisplayPage
from .pages.environment import EnvironmentPage
from .pages.hyprland import HyprlandPage
from .pages.network import NetworkPage
from .pages.overview import OverviewPage
from .pages.packages import PackagesPage
from .pages.power import PowerPage
from .pages.processes import ProcessesPage
from .pages.security import SecurityPage
from .pages.storage import StoragePage
from .settings_dialog import SettingsDialog
from .sidebar import NavItem, Sidebar
from .theme import Palette, apply_theme, load_palette
from .widgets import ToastManager, theme_icon


@dataclass(frozen=True, slots=True)
class PageSpec:
    title: str
    icon: str
    fallback: QStyle.StandardPixmap
    page_class: type


PAGE_SPECS: list[PageSpec] = [
    PageSpec("Overview", "computer-symbolic", QStyle.StandardPixmap.SP_ComputerIcon, OverviewPage),
    PageSpec(
        "Network", "network-workgroup-symbolic", QStyle.StandardPixmap.SP_DriveNetIcon, NetworkPage
    ),
    PageSpec(
        "Display", "video-display-symbolic", QStyle.StandardPixmap.SP_DesktopIcon, DisplayPage
    ),
    PageSpec(
        "Audio", "audio-volume-high-symbolic", QStyle.StandardPixmap.SP_MediaVolume, AudioPage
    ),
    PageSpec("Power", "battery-symbolic", QStyle.StandardPixmap.SP_DialogApplyButton, PowerPage),
    PageSpec(
        "Appearance",
        "preferences-desktop-wallpaper-symbolic",
        QStyle.StandardPixmap.SP_FileDialogContentsView,
        AppearancePage,
    ),
    PageSpec(
        "Hyprland",
        "preferences-system-windows-symbolic",
        QStyle.StandardPixmap.SP_TitleBarMaxButton,
        HyprlandPage,
    ),
    PageSpec(
        "Processes",
        "view-process-all-symbolic",
        QStyle.StandardPixmap.SP_BrowserReload,
        ProcessesPage,
    ),
    PageSpec(
        "Packages", "package-x-generic-symbolic", QStyle.StandardPixmap.SP_DirIcon, PackagesPage
    ),
    PageSpec(
        "Storage", "drive-harddisk-symbolic", QStyle.StandardPixmap.SP_DriveHDIcon, StoragePage
    ),
    PageSpec(
        "Bluetooth", "bluetooth-symbolic", QStyle.StandardPixmap.SP_CommandLink, BluetoothPage
    ),
    PageSpec(
        "Security",
        "security-high-symbolic",
        QStyle.StandardPixmap.SP_MessageBoxWarning,
        SecurityPage,
    ),
    PageSpec(
        "Environment",
        "utilities-terminal-symbolic",
        QStyle.StandardPixmap.SP_ComputerIcon,
        EnvironmentPage,
    ),
]


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: SettingsStore,
        settings: Settings,
        runner: CommandRunner,
        palette: Palette,
        *,
        ui_font: str = "Sans Serif",
        mono_font: str = "Monospace",
    ) -> None:
        super().__init__()
        self.store = store
        self.settings = settings
        self.runner = runner
        self.palette = palette
        self.ui_font = ui_font
        self.mono_font = mono_font
        self._panels: list[QWidget | None] = [None] * len(PAGE_SPECS)
        self._last_stats: Stats | None = None
        self._closing = False
        self.panel_errors = 0
        self._user_sidebar_pref = settings.sidebar_collapsed
        self._adjusting_sidebar = False

        self.setWindowTitle(__app_name__)
        self.setWindowIcon(theme_icon("preferences-system", QStyle.StandardPixmap.SP_ComputerIcon))
        self.setMinimumSize(760, 540)
        self.setObjectName("MainWindow")

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        items = [NavItem(spec.title, spec.icon, spec.fallback) for spec in PAGE_SPECS]
        self.sidebar = Sidebar(items)
        self.sidebar.page_selected.connect(self.switch_page)
        self.sidebar.collapsed_changed.connect(self._on_sidebar_collapsed)
        self.sidebar.toggled_by_user.connect(self._on_sidebar_toggled)
        self.sidebar.settings_requested.connect(self.open_settings)
        root_layout.addWidget(self.sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.stack = QStackedWidget()
        for spec in PAGE_SPECS:
            self.stack.addWidget(self._placeholder(spec.title))
        right_layout.addWidget(self.stack, 1)
        right_layout.addWidget(self._build_footer())
        root_layout.addWidget(right, 1)

        self.toasts = ToastManager(root)
        self.stats_worker = StatsWorker(settings.refresh_ms, self)
        self.stats_worker.stats_ready.connect(self._on_stats)
        self.stats_worker.start()

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(15_000)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start()
        self._update_clock()

        geometry = settings.window_geometry
        restored = False
        if geometry:
            try:
                restored = self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except (ValueError, UnicodeEncodeError):
                restored = False
        if not restored:
            self.resize(1240, 820)
        self.sidebar.set_collapsed(self.should_begin_collapsed(), emit=False)

        QTimer.singleShot(0, lambda: self.switch_page(self._initial_page()))
        self._install_shortcuts()

    # ------------------------------------------------------------------
    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("Footer")
        footer.setFixedHeight(30)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(16)
        self.footer_cpu = QLabel("CPU —")
        self.footer_mem = QLabel("RAM —")
        self.footer_net = QLabel("NET —")
        desktop = "Hyprland" if is_hyprland() else os.environ.get("XDG_CURRENT_DESKTOP", "Linux")
        self.footer_compositor = QLabel(desktop or "Linux")
        self.footer_clock = QLabel("")
        for label in (self.footer_cpu, self.footer_mem, self.footer_net):
            label.setObjectName("FooterLabel")
            layout.addWidget(label)
        layout.addStretch()
        self.footer_compositor.setObjectName("FooterAccent")
        self.footer_clock.setObjectName("FooterLabel")
        layout.addWidget(self.footer_compositor)
        layout.addWidget(self.footer_clock)
        return footer

    def _placeholder(self, title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(f"Loading {title}…")
        label.setObjectName("Muted")
        layout.addWidget(label)
        return page

    def _initial_page(self) -> int:
        index = self.settings.last_page
        return index if 0 <= index < len(PAGE_SPECS) else 0

    def _install_shortcuts(self) -> None:
        for index in range(min(9, len(PAGE_SPECS))):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda i=index: self.switch_page(i))
        preferences = QShortcut(QKeySequence("Ctrl+,"), self)
        preferences.activated.connect(self.open_settings)
        refresh = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh.activated.connect(self.refresh_current)
        quit_shortcut = QShortcut(QKeySequence.StandardKey.Quit, self)
        quit_shortcut.activated.connect(self.close)

    # ------------------------------------------------------------------
    def switch_page(self, index: int) -> None:
        if not 0 <= index < len(PAGE_SPECS):
            return
        panel = self._build_panel(index)
        self.stack.setCurrentWidget(panel)
        self.sidebar.set_current(index)
        self.settings.last_page = index
        self._save_settings()

    def _build_panel(self, index: int) -> QWidget:
        existing = self._panels[index]
        if existing is not None:
            return existing

        spec = PAGE_SPECS[index]
        old = self.stack.widget(index)
        try:
            panel = spec.page_class(
                self.runner,
                self.settings,
                palette=self.palette,
                mono_font=self.mono_font,
                parent=self,
            )
        except Exception:
            traceback.print_exc()
            self.panel_errors += 1
            panel = self._error_page(spec.title, index)
            self.notify(f"Could not load {spec.title}. See the terminal for details.", "error")
        self._panels[index] = panel
        self.stack.insertWidget(index, panel)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        return panel

    def _error_page(self, title: str, index: int) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel(f"{title} could not be loaded")
        heading.setStyleSheet("font-size: 17px; font-weight: 700;")
        detail = QLabel("Open the application from a terminal to see the error, then retry.")
        detail.setObjectName("Muted")
        retry = QPushButton("Retry")
        retry.clicked.connect(lambda: self._retry_panel(index))
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addWidget(retry)
        return page

    def _retry_panel(self, index: int) -> None:
        old = self._panels[index]
        self._panels[index] = None
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()
        self.stack.insertWidget(index, self._placeholder(PAGE_SPECS[index].title))
        self.switch_page(index)

    def refresh_current(self) -> None:
        panel = self.stack.currentWidget()
        refresh = getattr(panel, "refresh", None)
        if callable(refresh):
            refresh()
        else:
            self.notify("This page has no refresh action.", "info")

    # ------------------------------------------------------------------
    def _on_stats(self, stats: Stats) -> None:
        self._last_stats = stats
        self.footer_cpu.setText(f"CPU {stats.cpu:.0f}%")
        self.footer_mem.setText(f"RAM {stats.mem_percent:.0f}%")
        self.footer_net.setText(
            f"NET ↓ {format_rate(stats.net_down)} · ↑ {format_rate(stats.net_up)}"
        )
        for panel in self._panels:
            if panel is None:
                continue
            update = getattr(panel, "update_stats", None)
            if callable(update):
                update(stats)

    def _update_clock(self) -> None:
        self.footer_clock.setText(datetime.now().strftime("%a %d %b · %H:%M"))

    # ------------------------------------------------------------------
    def notify(self, message: str, level: str = "info", timeout_ms: int = 3800) -> None:
        self.toasts.show(message, level, timeout_ms)

    def reload_theme(self) -> None:
        self.palette = load_palette(self.settings.accent)
        app = QApplication.instance()
        if app is not None:
            self.ui_font, self.mono_font = apply_theme(app, self.palette)
        for panel in self._panels:
            if panel is None:
                continue
            update = getattr(panel, "set_palette", None)
            if callable(update):
                update(self.palette)
        self.update()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if not dialog.exec():
            return
        updated = dialog.result_settings()
        for field in dataclasses.fields(self.settings):
            setattr(self.settings, field.name, getattr(updated, field.name))
        self._save_settings()
        self.stats_worker.set_interval(self.settings.refresh_ms)
        self._user_sidebar_pref = self.settings.sidebar_collapsed
        self.reload_theme()
        self.notify("Preferences saved.", "success")

    # ------------------------------------------------------------------
    def _save_settings(self) -> None:
        if self._closing:
            return
        with contextlib.suppress(OSError):
            self.store.save(self.settings)

    def _on_sidebar_collapsed(self, collapsed: bool) -> None:
        if self._adjusting_sidebar:
            return
        self.settings.sidebar_collapsed = collapsed
        self._save_settings()

    def _on_sidebar_toggled(self, collapsed: bool) -> None:
        self._user_sidebar_pref = collapsed

    def should_begin_collapsed(self) -> bool:
        return self.settings.sidebar_collapsed or self.width() < 940

    def _adjust_sidebar(self) -> None:
        if self._adjusting_sidebar:
            return
        self._adjusting_sidebar = True
        try:
            if self.width() < 900 and not self.sidebar.is_collapsed():
                self.sidebar.set_collapsed(True)
            elif (
                self.width() > 1120 and not self._user_sidebar_pref and self.sidebar.is_collapsed()
            ):
                self.sidebar.set_collapsed(False)
        finally:
            self._adjusting_sidebar = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adjust_sidebar()
        self.toasts.reposition()

    def closeEvent(self, event) -> None:
        if self._closing:
            super().closeEvent(event)
            return
        self._closing = True
        try:
            self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.settings.sidebar_collapsed = self.sidebar.is_collapsed()
            self.store.save(self.settings)
        except OSError:
            pass
        self.stats_worker.stop()
        self.stats_worker.wait(1500)
        for panel in self._panels:
            if panel is not None:
                shutdown = getattr(panel, "shutdown", None)
                if callable(shutdown):
                    shutdown()
        self.runner.shutdown(1500)
        super().closeEvent(event)
