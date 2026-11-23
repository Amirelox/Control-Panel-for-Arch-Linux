"""Appearance page: wallpapers, Matugen colours, GTK themes and fonts."""

from __future__ import annotations

import random
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont, QIcon, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import appearance, wallpaper
from ...core.commands import CommandRunner
from ...core.config import Settings, hypr_colors_conf
from ..theme import load_palette
from ..widgets import BasePage, Card


class AppearancePage(BasePage):
    title = "Appearance"
    subtitle = "Wallpapers, dynamic colours and desktop themes"
    icon_name = "preferences-desktop-wallpaper-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_FileDialogContentsView

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
        self._wallpapers: list[Path] = []
        self._thumbnails_loaded = 0

        self.add_action_button(
            "Rescan",
            self.load_wallpapers,
            icon="view-refresh",
            style="Ghost",
            tooltip="Rescan wallpaper folders",
        )

        tabs = QTabWidget()
        tabs.addTab(self._build_wallpaper_tab(), "Wallpaper")
        tabs.addTab(self._build_colours_tab(), "Colours")
        tabs.addTab(self._build_themes_tab(), "Themes")
        tabs.addTab(self._build_font_tab(), "Fonts")
        tabs.setMinimumHeight(420)
        self.add(tabs, 1)

    # ------------------------------------------------------------------
    def _build_wallpaper_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(10)

        self.backend_hint = QLabel("")
        self.backend_hint.setObjectName("Hint")
        self.backend_hint.setWordWrap(True)
        layout.addWidget(self.backend_hint)

        self.wall_list = QListWidget()
        self.wall_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.wall_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.wall_list.setFlow(QListWidget.Flow.LeftToRight)
        self.wall_list.setWrapping(True)
        self.wall_list.setMovement(QListWidget.Movement.Static)
        self.wall_list.setIconSize(QSize(176, 99))
        self.wall_list.setGridSize(QSize(196, 136))
        self.wall_list.setSpacing(6)
        self.wall_list.setWordWrap(True)
        self.wall_list.setMinimumHeight(300)
        self.wall_list.itemDoubleClicked.connect(lambda _item: self.apply_selected())
        layout.addWidget(self.wall_list, 1)

        self.regenerate_check = QCheckBox("Regenerate accent colours with Matugen")
        self.regenerate_check.setChecked(True)
        layout.addWidget(self.regenerate_check)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        apply_btn = QPushButton("Apply wallpaper")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self.apply_selected)
        random_btn = QPushButton("Random")
        random_btn.clicked.connect(self.apply_random)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.browse_wallpaper)
        folder_btn = QPushButton("Open folder")
        folder_btn.setObjectName("Ghost")
        folder_btn.clicked.connect(self.open_folder)
        buttons.addWidget(apply_btn)
        buttons.addWidget(random_btn)
        buttons.addWidget(browse_btn)
        buttons.addWidget(folder_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        return page

    def _build_colours_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(12)

        card = Card("Current palette")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.accent_swatch = QFrame()
        self.accent_swatch.setFixedSize(42, 42)
        row.addWidget(self.accent_swatch)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.accent_name = QLabel("—")
        self.accent_name.setStyleSheet("font-weight: 700; font-size: 15px;")
        self.accent_path = QLabel(str(hypr_colors_conf()))
        self.accent_path.setObjectName("Hint")
        info.addWidget(self.accent_name)
        info.addWidget(self.accent_path)
        row.addLayout(info, 1)
        card.add_layout(row)

        regenerate = QPushButton("Regenerate colours from wallpaper")
        regenerate.setObjectName("Primary")
        regenerate.clicked.connect(self.regenerate_colours)
        card.add(regenerate)
        self.colour_hint = QLabel(
            "Matugen generates a Material You palette from the current wallpaper. "
            "Hyprland and Quickshell are reloaded afterwards."
        )
        self.colour_hint.setObjectName("Hint")
        self.colour_hint.setWordWrap(True)
        card.add(self.colour_hint)
        layout.addWidget(card)
        layout.addStretch()
        self._refresh_accent()
        return page

    def _build_themes_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(12)

        gtk_card = Card("GTK theme and icons")
        gtk_row = QHBoxLayout()
        gtk_row.setSpacing(10)
        self.gtk_combo = QComboBox()
        self.gtk_combo.setEditable(True)
        self.gtk_combo.setMinimumWidth(210)
        self.icons_combo = QComboBox()
        self.icons_combo.setEditable(True)
        self.icons_combo.setMinimumWidth(210)
        gtk_row.addWidget(QLabel("GTK theme"))
        gtk_row.addWidget(self.gtk_combo, 1)
        gtk_row.addWidget(QLabel("Icons"))
        gtk_row.addWidget(self.icons_combo, 1)
        gtk_card.add_layout(gtk_row)
        apply_gtk = QPushButton("Apply GTK theme")
        apply_gtk.setObjectName("Primary")
        apply_gtk.clicked.connect(self.apply_gtk)
        gtk_card.add(apply_gtk)
        layout.addWidget(gtk_card)

        cursor_card = Card("Mouse cursor")
        cursor_row = QHBoxLayout()
        cursor_row.setSpacing(10)
        self.cursor_combo = QComboBox()
        self.cursor_combo.setEditable(True)
        self.cursor_combo.setMinimumWidth(240)
        cursor_row.addWidget(QLabel("Cursor theme"))
        cursor_row.addWidget(self.cursor_combo, 1)
        cursor_card.add_layout(cursor_row)
        apply_cursor = QPushButton("Apply cursor")
        apply_cursor.clicked.connect(self.apply_cursor)
        cursor_card.add(apply_cursor)
        layout.addWidget(cursor_card)
        layout.addStretch()
        return page

    def _build_font_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 2, 2)
        layout.setSpacing(12)

        card = Card("Interface font")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.font_combo = QFontComboBox()
        self.font_combo.setMinimumWidth(240)
        self.font_size = QSpinBox()
        self.font_size.setRange(7, 28)
        self.font_size.setValue(11)
        row.addWidget(QLabel("Family"))
        row.addWidget(self.font_combo, 1)
        row.addWidget(QLabel("Size"))
        row.addWidget(self.font_size)
        card.add_layout(row)
        apply_font = QPushButton("Apply font")
        apply_font.setObjectName("Primary")
        apply_font.clicked.connect(self.apply_font)
        card.add(apply_font)
        hint = QLabel("Applied through gsettings for GTK applications.")
        hint.setObjectName("Hint")
        card.add(hint)
        layout.addWidget(card)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.load_wallpapers()
            self._load_theme_options()

    def load_wallpapers(self) -> None:
        self.wall_list.clear()
        self._thumbnails_loaded = 0
        self.wall_list.addItem("Scanning wallpaper folders…")
        backend = wallpaper.wallpaper_backend()
        self.backend_hint.setText(
            f"Backend: {backend}"
            if backend
            else "No wallpaper backend found. Install awww, swww, hyprpaper or swaybg."
        )

        def scan() -> list[Path]:
            return wallpaper.find_wallpapers()

        def done(paths: list[Path]) -> None:
            self.wall_list.clear()
            self._wallpapers = paths
            if not paths:
                self.wall_list.addItem("No wallpapers found.")
                return
            current = wallpaper.current_wallpaper()
            for index, path in enumerate(paths):
                item = QListWidgetItem(path.name)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                item.setToolTip(str(path))
                item.setSizeHint(QSize(190, 132))
                if current is not None and path == current:
                    item.setText(f"{path.name}\n● current")
                self.wall_list.addItem(item)
                if index < 100:
                    self._load_thumbnail(path)
            self.backend_hint.setText(
                f"Backend: {wallpaper.wallpaper_backend()} · {len(paths)} wallpaper(s)"
            )

        self.call(scan, done)

    def _load_thumbnail(self, path: Path) -> None:
        def load() -> object:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                target = size.scaled(QSize(352, 198), Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(target)
            return reader.read()

        def done(image) -> None:
            if image is None or image.isNull():
                return
            for index in range(self.wall_list.count()):
                item = self.wall_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == str(path):
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
                    return

        self._thumbnails_loaded += 1
        self.runner.submit(load, on_done=done)

    def _selected_path(self) -> Path | None:
        item = self.wall_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return Path(data) if data else None

    def apply_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            self.notify("Select a wallpaper first.", "info")
            return
        self._apply_wallpaper(path)

    def apply_random(self) -> None:
        if not self._wallpapers:
            return
        self._apply_wallpaper(random.choice(self._wallpapers))

    def browse_wallpaper(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Choose wallpaper",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.avif)",
        )
        if selected:
            self._apply_wallpaper(Path(selected))

    def _apply_wallpaper(self, path: Path) -> None:
        regenerate = self.regenerate_check.isChecked()

        def work() -> tuple[bool, str]:
            return wallpaper.apply_wallpaper(path, regenerate_colours=regenerate)

        def done(result: tuple[bool, str]) -> None:
            ok, message = result
            self.notify(message, "success" if ok else "error")
            if ok:
                self._refresh_accent()
                self._reload_theme()
                self.load_wallpapers()

        self.call(work, done)

    def open_folder(self) -> None:
        selected = self._selected_path()
        if selected is not None:
            target = selected.parent
        else:
            directories = wallpaper.directories()
            target = directories[0] if directories else Path.home()
        from ...core.commands import spawn

        if spawn(["xdg-open", str(target)]) is None:
            self.notify(f"Could not open {target}", "error")

    def regenerate_colours(self) -> None:
        path = self._selected_path() or wallpaper.current_wallpaper()

        def done(result: tuple[bool, str]) -> None:
            ok, message = result
            self.colour_hint.setText(message)
            self.notify(message, "success" if ok else "error")
            if ok:
                self._refresh_accent()
                self._reload_theme()

        self.call(lambda: wallpaper.regenerate_colours(path), done)

    def set_palette(self, _palette) -> None:
        self._refresh_accent()

    def _refresh_accent(self) -> None:
        palette = load_palette(self.settings.accent)
        self.accent_name.setText(palette.accent.upper())
        self.accent_swatch.setStyleSheet(
            f"background: {palette.accent}; border-radius: 12px; "
            f"border: 1px solid {palette.border};"
        )

    def _reload_theme(self) -> None:
        reload_theme = getattr(self.window(), "reload_theme", None)
        if callable(reload_theme):
            reload_theme()

    # ------------------------------------------------------------------
    def _load_theme_options(self) -> None:
        def work():
            return (
                appearance.list_themes(),
                appearance.list_icon_themes(),
                appearance.list_cursor_themes(),
                appearance.current_settings(),
            )

        def done(values) -> None:
            themes, icons, cursors, current = values
            self.gtk_combo.clear()
            self.gtk_combo.addItems(themes)
            self.icons_combo.clear()
            self.icons_combo.addItems(icons)
            self.cursor_combo.clear()
            self.cursor_combo.addItems(cursors)
            if current.get("gtk-theme"):
                self.gtk_combo.setCurrentText(current["gtk-theme"])
            if current.get("icon-theme"):
                self.icons_combo.setCurrentText(current["icon-theme"])
            if current.get("cursor-theme"):
                self.cursor_combo.setCurrentText(current["cursor-theme"])
            font_name = current.get("font-name", "")
            if font_name:
                family = font_name.rsplit(" ", 1)[0] if " " in font_name else font_name
                self.font_combo.setCurrentFont(QFont(family))
                tail = font_name.rsplit(" ", 1)[-1]
                if tail.isdigit():
                    self.font_size.setValue(max(7, min(28, int(tail))))

        self.call(work, done)

    def apply_gtk(self) -> None:
        theme = self.gtk_combo.currentText().strip()
        icons = self.icons_combo.currentText().strip()

        def done(result) -> None:
            self.notify(
                "GTK theme applied." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )

        self.call(lambda: appearance.apply_gtk(theme, icons), done)

    def apply_cursor(self) -> None:
        cursor = self.cursor_combo.currentText().strip()

        def done(result) -> None:
            self.notify(
                "Cursor theme applied. Log out and back in for all apps."
                if result.ok
                else result.summary(),
                "success" if result.ok else "error",
            )

        self.call(lambda: appearance.apply_cursor(cursor), done)

    def apply_font(self) -> None:
        family = self.font_combo.currentFont().family()
        value = f"{family} {self.font_size.value()}"

        def done(result) -> None:
            self.notify(
                "Interface font applied." if result.ok else result.summary(),
                "success" if result.ok else "error",
            )

        self.call(lambda: appearance.apply_font(value), done)
