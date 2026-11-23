"""Colours, fonts and the application stylesheet."""

from __future__ import annotations

import re
from dataclasses import dataclass

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

from ..core.config import hypr_colors_conf
from ..core.fs import read_text

__all__ = ["Palette", "apply_theme", "build_stylesheet", "load_palette", "pick_fonts"]

_ACCENTS = {
    "violet": ("#d9b8ff", "#b79be0"),
    "green": ("#cbe69a", "#9fbf72"),
    "blue": ("#9cc7ff", "#78a6e0"),
    "rose": ("#ffb8c8", "#e39aab"),
}


@dataclass(frozen=True, slots=True)
class Palette:
    bg: str = "#0f0d12"
    surface: str = "#171419"
    surface_alt: str = "#1f1b23"
    raised: str = "#27222d"
    border: str = "#302a38"
    text: str = "#ece7ef"
    muted: str = "#a89fae"
    accent: str = "#d9b8ff"
    accent_2: str = "#b79be0"
    accent_fg: str = "#1a1024"
    success: str = "#a6e3a1"
    warning: str = "#f9e2af"
    danger: str = "#f38ba8"
    info: str = "#89b4fa"
    shadow: str = "#00000066"

    @property
    def accent_soft(self) -> str:
        return _mix(self.surface, self.accent, 0.16)

    @property
    def success_soft(self) -> str:
        return _mix(self.surface, self.success, 0.14)

    @property
    def danger_soft(self) -> str:
        return _mix(self.surface, self.danger, 0.14)


def _normalise_hex(value: str) -> str | None:
    raw = value.strip()
    # Hyprland accepts rgb(cbe69a), rgba(cbe69aff), #cbe69a and 0xffcbe69a.
    match = re.search(r"rgba?\(\s*([0-9a-fA-F]{6,8})\s*\)", raw)
    if match:
        return "#" + match.group(1)[:6].lower()
    lowered = raw.lower()
    if lowered.startswith("0x"):
        digits = lowered[2:]
        if len(digits) in {6, 8}:
            # 0xAARRGGBB -> keep RGB
            return "#" + (digits[-6:] if len(digits) == 8 else digits)
        return None
    if lowered.startswith("#"):
        digits = lowered[1:]
        if len(digits) in {6, 8}:
            # CSS #RRGGBBAA -> keep RGB
            return "#" + digits[:6]
    return None


def _mix(first: str, second: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    a = QColor(first)
    b = QColor(second)
    red = round(a.red() * (1 - amount) + b.red() * amount)
    green = round(a.green() * (1 - amount) + b.green() * amount)
    blue = round(a.blue() * (1 - amount) + b.blue() * amount)
    return QColor(red, green, blue).name()


def _is_light(color: str) -> bool:
    value = QColor(color)
    return (value.red() * 299 + value.green() * 587 + value.blue() * 114) / 1000 > 150


def _parse_hypr_colors() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(hypr_colors_conf()).splitlines():
        stripped = line.strip()
        if not stripped.startswith("$") or "=" not in stripped:
            continue
        key, value = stripped[1:].split("=", 1)
        colour = _normalise_hex(value)
        if colour:
            values[key.strip()] = colour
    return values


def load_palette(accent_mode: str = "auto") -> Palette:
    hypr = _parse_hypr_colors()
    base = Palette()
    if accent_mode == "auto":
        accent = hypr.get("accent", base.accent)
        accent_2 = hypr.get("accent2", base.accent_2)
    else:
        accent, accent_2 = _ACCENTS.get(accent_mode, _ACCENTS["violet"])

    bg = hypr.get("bg", base.bg)
    # Matugen's background can be very close to black; keep a little depth.
    if _is_light(bg):
        bg = base.bg
    surface = _mix(bg, "#ffffff", 0.055)
    surface_alt = _mix(bg, "#ffffff", 0.10)
    raised = _mix(bg, "#ffffff", 0.15)
    border = _mix(bg, "#ffffff", 0.18)
    text = hypr.get("fg", base.text)
    if not _is_light(text):
        text = base.text
    muted = _mix(text, bg, 0.38)

    return Palette(
        bg=bg,
        surface=surface,
        surface_alt=surface_alt,
        raised=raised,
        border=border,
        text=text,
        muted=muted,
        accent=accent,
        accent_2=accent_2,
        accent_fg="#151016" if _is_light(accent) else "#ffffff",
        success=hypr.get("success", base.success),
        danger=hypr.get("error", base.danger),
        shadow="#00000080",
    )


def pick_fonts() -> tuple[str, str]:
    families = set(QFontDatabase.families())
    ui_candidates = (
        "Inter",
        "Adwaita Sans",
        "Cantarell",
        "Noto Sans",
        "Liberation Sans",
        "DejaVu Sans",
    )
    mono_candidates = (
        "JetBrainsMono Nerd Font",
        "JetBrains Mono",
        "CaskaydiaCove Nerd Font",
        "FiraCode Nerd Font",
        "Cascadia Code",
        "Source Code Pro",
        "DejaVu Sans Mono",
    )
    ui = next((name for name in ui_candidates if name in families), "Sans Serif")
    mono = next((name for name in mono_candidates if name in families), "Monospace")
    return ui, mono


def build_stylesheet(palette: Palette, ui_font: str, mono_font: str) -> str:
    p = palette
    scroll_handle = _mix(p.border, p.accent, 0.25)
    selection = p.accent_soft
    return f"""
    * {{
        font-family: "{ui_font}";
        font-size: 13px;
        outline: none;
    }}
    QMainWindow, QDialog, QWidget#Root {{
        background: {p.bg};
        color: {p.text};
    }}
    QWidget {{ color: {p.text}; }}
    QToolTip {{
        background: {p.raised};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 5px 8px;
    }}
    QWidget#Sidebar {{
        background: {p.surface};
        border-right: 1px solid {p.border};
    }}
    QLabel#Logo {{
        color: {p.accent};
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }}
    QLabel#LogoCompact {{
        color: {p.accent};
        font-size: 16px;
        font-weight: 800;
    }}
    QLabel#AppSubtitle {{
        color: {p.muted};
        font-size: 11px;
    }}
    QLabel#PageTitle {{
        font-size: 25px;
        font-weight: 700;
        color: {p.text};
    }}
    QLabel#PageSubtitle {{
        color: {p.muted};
        font-size: 12px;
    }}
    QLabel#SectionTitle {{
        color: {p.accent};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#Muted {{ color: {p.muted}; }}
    QLabel#StatValue {{
        color: {p.text};
        font-size: 24px;
        font-weight: 700;
    }}
    QLabel#StatTitle {{
        color: {p.muted};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#Hint {{ color: {p.muted}; font-size: 11px; }}
    QLabel#Danger {{ color: {p.danger}; }}
    QLabel#Success {{ color: {p.success}; }}
    QLabel#Accent {{ color: {p.accent}; }}
    QFrame#Card, QFrame#StatCard {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 13px;
    }}
    QFrame#Card QLabel, QFrame#StatCard QLabel {{ background: transparent; }}
    QFrame#Card:hover, QFrame#StatCard:hover {{ border-color: {_mix(p.border, p.accent, 0.35)}; }}
    QFrame#Divider {{ background: {p.border}; max-height: 1px; border: none; }}
    QFrame#Pill {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 10px;
    }}
    QGroupBox {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 12px;
        margin-top: 14px;
        padding: 16px 12px 12px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: 2px;
        padding: 0 5px;
        color: {p.muted};
        background: {p.bg};
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 9px;
        padding: 7px 14px;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background: {p.raised};
        border-color: {_mix(p.border, p.accent, 0.35)};
    }}
    QPushButton:pressed {{ background: {_mix(p.raised, "#000000", 0.15)}; }}
    QPushButton:disabled {{
        background: {p.surface};
        color: {_mix(p.muted, p.surface, 0.45)};
        border-color: {p.border};
    }}
    QPushButton:focus {{ border-color: {p.accent}; }}
    QPushButton#Primary {{
        background: {p.accent};
        color: {p.accent_fg};
        border: 1px solid transparent;
        font-weight: 700;
    }}
    QPushButton#Primary:hover {{ background: {p.accent_2}; }}
    QPushButton#Primary:pressed {{ background: {_mix(p.accent_2, "#000000", 0.15)}; }}
    QPushButton#Primary:disabled {{
        background: {_mix(p.surface_alt, p.accent, 0.20)};
        color: {_mix(p.muted, p.accent_fg, 0.35)};
    }}
    QPushButton#Danger {{ background: {p.danger_soft}; color: {p.danger}; border-color: {_mix(p.danger, p.border, 0.35)}; }}
    QPushButton#Danger:hover {{ background: {_mix(p.surface, p.danger, 0.26)}; }}
    QPushButton#Success {{ background: {p.success_soft}; color: {p.success}; border-color: {_mix(p.success, p.border, 0.35)}; }}
    QPushButton#Success:hover {{ background: {_mix(p.surface, p.success, 0.26)}; }}
    QPushButton#Ghost {{ background: transparent; border-color: transparent; color: {p.muted}; }}
    QPushButton#Ghost:hover {{ background: {p.surface_alt}; color: {p.text}; }}
    QPushButton#NavButton {{
        background: transparent;
        border: none;
        border-radius: 10px;
        padding: 9px 12px;
        color: {p.muted};
        text-align: left;
        font-weight: 500;
    }}
    QPushButton#NavButton:hover {{ background: {p.surface_alt}; color: {p.text}; }}
    QPushButton#NavButton:checked {{
        background: {p.accent_soft};
        color: {p.accent};
        font-weight: 700;
    }}
    QPushButton#NavButton:checked:hover {{ background: {p.accent_soft}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {scroll_handle};
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.accent_2}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {scroll_handle}; border-radius: 4px; min-width: 28px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 6px 9px;
        selection-background-color: {p.accent};
        selection-color: {p.accent_fg};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus, QComboBox:on {{
        border-color: {_mix(p.accent, p.border, 0.35)};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
    QSpinBox:disabled, QComboBox:disabled {{ color: {p.muted}; background: {p.surface}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        selection-background-color: {selection};
        selection-color: {p.text};
        padding: 4px;
        outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; background: transparent; }}
    QSlider::groove:horizontal {{ height: 5px; background: {p.surface_alt}; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 3px; }}
    QSlider::add-page:horizontal {{ background: {p.surface_alt}; border-radius: 3px; }}
    QSlider::handle:horizontal {{
        background: {p.accent};
        width: 15px;
        height: 15px;
        margin: -6px 0;
        border-radius: 8px;
        border: 2px solid {p.bg};
    }}
    QSlider::handle:horizontal:hover {{ background: {p.accent_2}; }}
    QProgressBar {{
        background: {p.surface_alt};
        border: none;
        border-radius: 5px;
        min-height: 8px;
        max-height: 10px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 5px; }}
    QCheckBox, QRadioButton {{ spacing: 8px; color: {p.text}; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 5px;
        border: 1px solid {p.border};
        background: {p.surface_alt};
    }}
    QCheckBox::indicator:checked {{
        background: {p.accent};
        border-color: {p.accent};
    }}
    QCheckBox::indicator:disabled {{ background: {p.surface}; }}
    QTreeWidget, QListWidget, QTableWidget {{
        background: {p.surface};
        alternate-background-color: {_mix(p.surface, p.bg, 0.35)};
        border: 1px solid {p.border};
        border-radius: 9px;
        color: {p.text};
        gridline-color: {p.border};
        selection-background-color: {selection};
        selection-color: {p.text};
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 4px 2px; border: none; }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {p.surface_alt}; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {selection};
        color: {p.text};
    }}
    QListWidget::item:selected:!active, QTreeWidget::item:selected:!active {{ background: {selection}; }}
    QHeaderView::section {{
        background: {p.surface_alt};
        color: {p.muted};
        padding: 7px 8px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-size: 11px;
        font-weight: 700;
    }}
    QTableCornerButton::section {{ background: {p.surface_alt}; border: none; }}
    QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 10px; background: {p.surface}; top: -1px; }}
    QTabBar::tab {{
        background: transparent;
        color: {p.muted};
        padding: 8px 16px;
        margin-right: 2px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{ color: {p.text}; }}
    QTabBar::tab:selected {{ color: {p.accent}; border-bottom-color: {p.accent}; font-weight: 600; }}
    QMenu {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 5px;
    }}
    QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {selection}; }}
    QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}
    QStatusBar {{ background: {p.surface}; color: {p.muted}; border-top: 1px solid {p.border}; }}
    QStatusBar::item {{ border: none; }}
    QWidget#Footer {{ background: {p.surface}; border-top: 1px solid {p.border}; }}
    QLabel#FooterLabel {{ color: {p.muted}; font-size: 11px; }}
    QLabel#FooterAccent {{ color: {p.accent}; font-size: 11px; font-weight: 600; }}
    QSplitter::handle {{ background: {p.border}; }}
    QFrame#Toast {{
        background: {p.raised};
        border: 1px solid {p.border};
        border-radius: 10px;
    }}
    QLabel#ToastText {{ color: {p.text}; font-weight: 500; }}
    QScrollArea#CodeScroll {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 9px; }}
    QPlainTextEdit#CodeEditor {{
        background: {p.bg};
        color: {p.text};
        font-family: "{mono_font}";
        font-size: 12px;
        border: none;
        border-radius: 0;
        padding: 8px;
    }}
    QDialogButtonBox QPushButton {{ min-width: 80px; }}
    """


def apply_theme(app: QApplication, palette: Palette) -> tuple[str, str]:
    """Install the palette, font and stylesheet on *app*.

    Returns the selected ``(ui_font, mono_font)`` families so pages can reuse
    them for code editors and previews.
    """
    ui_font, mono_font = pick_fonts()

    qt_palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: palette.bg,
        QPalette.ColorRole.WindowText: palette.text,
        QPalette.ColorRole.Base: palette.surface,
        QPalette.ColorRole.AlternateBase: palette.surface_alt,
        QPalette.ColorRole.Text: palette.text,
        QPalette.ColorRole.Button: palette.surface_alt,
        QPalette.ColorRole.ButtonText: palette.text,
        QPalette.ColorRole.Highlight: palette.accent,
        QPalette.ColorRole.HighlightedText: palette.accent_fg,
        QPalette.ColorRole.ToolTipBase: palette.raised,
        QPalette.ColorRole.ToolTipText: palette.text,
        QPalette.ColorRole.PlaceholderText: palette.muted,
        QPalette.ColorRole.Link: palette.accent,
    }
    for role, colour in roles.items():
        qt_palette.setColor(role, QColor(colour))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        qt_palette.setColor(
            QPalette.ColorGroup.Disabled, role, QColor(_mix(palette.muted, palette.bg, 0.35))
        )

    base_font = QFont(ui_font)
    base_font.setPointSizeF(10.0)
    base_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(base_font)
    app.setPalette(qt_palette)
    app.setStyleSheet(build_stylesheet(palette, ui_font, mono_font))
    return ui_font, mono_font
