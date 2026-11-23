"""Colours, fonts and the application stylesheet.

The chrome is deliberately quiet: a graphite ramp, one amber signal colour and
a monospace face for figures. Matugen can still supply the accent when the user
chooses "auto"; surfaces never follow the wallpaper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

from ..core.config import hypr_colors_conf
from ..core.fs import read_text

__all__ = ["Palette", "apply_theme", "build_stylesheet", "load_palette", "pick_fonts"]

_ACCENTS = {
    "amber": ("#d6a45f", "#b8894e"),
    "violet": ("#b9a7d8", "#9b88bd"),
    "green": ("#9fc48a", "#82a86c"),
    "blue": ("#8fb6d9", "#6f97bc"),
    "rose": ("#d8a0aa", "#b9828c"),
}


@dataclass(frozen=True, slots=True)
class Palette:
    bg: str = "#0f1013"
    surface: str = "#16171b"
    surface_alt: str = "#1d1e23"
    raised: str = "#25262c"
    border: str = "#2c2d33"
    text: str = "#e9eaee"
    muted: str = "#989ba4"
    accent: str = "#d6a45f"
    accent_2: str = "#b8894e"
    accent_fg: str = "#17130c"
    success: str = "#83bd91"
    warning: str = "#d6a45f"
    danger: str = "#d97b7b"
    info: str = "#8aa9c9"
    shadow: str = "#00000080"

    @property
    def sidebar(self) -> str:
        return _mix(self.bg, "#000000", 0.28)

    @property
    def accent_soft(self) -> str:
        return _mix(self.surface, self.accent, 0.14)

    @property
    def success_soft(self) -> str:
        return _mix(self.surface, self.success, 0.12)

    @property
    def danger_soft(self) -> str:
        return _mix(self.surface, self.danger, 0.12)


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
            return "#" + (digits[-6:] if len(digits) == 8 else digits)
        return None
    if lowered.startswith("#"):
        digits = lowered[1:]
        if len(digits) in {6, 8}:
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


def load_palette(accent_mode: str = "amber") -> Palette:
    hypr = _parse_hypr_colors()
    base = Palette()
    if accent_mode == "auto":
        accent = hypr.get("accent", base.accent)
        accent_2 = hypr.get("accent2", base.accent_2)
    else:
        accent, accent_2 = _ACCENTS.get(accent_mode, _ACCENTS["amber"])

    return Palette(
        accent=accent,
        accent_2=accent_2,
        accent_fg="#17130c" if _is_light(accent) else "#ffffff",
    )


def pick_fonts() -> tuple[str, str]:
    families = set(QFontDatabase.families())
    ui_candidates = (
        "Adwaita Sans",
        "Cantarell",
        "Inter",
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
    scroll_handle = _mix(p.border, p.text, 0.22)
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
        padding: 6px 8px;
    }}

    /* Shell */
    QWidget#Sidebar {{
        background: {p.sidebar};
        border-right: 1px solid {p.border};
    }}
    QLabel#Logo {{
        color: {p.text};
        font-size: 18px;
        font-weight: 600;
    }}
    QLabel#LogoCompact {{
        color: {p.text};
        font-size: 15px;
        font-weight: 600;
    }}
    QLabel#AppSubtitle {{
        color: {p.muted};
        font-size: 12px;
    }}
    QPushButton#NavButton {{
        background: transparent;
        border: none;
        border-left: 2px solid transparent;
        border-radius: 8px;
        padding: 0 12px;
        min-height: 36px;
        color: {p.muted};
        text-align: left;
        font-size: 14px;
        font-weight: 400;
    }}
    QPushButton#NavButton:hover {{ background: {p.surface_alt}; color: {p.text}; }}
    QPushButton#NavButton:checked {{
        background: {p.surface_alt};
        border-left-color: {p.accent};
        color: {p.text};
        font-weight: 500;
    }}

    /* Page header */
    QLabel#PageEyebrow {{
        color: {p.muted};
        font-family: "{mono_font}";
        font-size: 11px;
    }}
    QLabel#PageTitle {{
        color: {p.text};
        font-size: 30px;
        font-weight: 500;
    }}
    QLabel#PageSubtitle {{
        color: {p.muted};
        font-size: 13px;
    }}
    QLabel#SectionTitle {{
        color: {p.muted};
        font-size: 13px;
        font-weight: 500;
    }}
    QLabel#Muted {{ color: {p.muted}; }}
    QLabel#Hint {{ color: {p.muted}; font-size: 12px; }}
    QLabel#MonoHint {{
        color: {p.muted};
        font-family: "{mono_font}";
        font-size: 11px;
    }}
    QLabel#CardTitle {{ color: {p.muted}; font-size: 12px; font-weight: 500; }}
    QLabel#Danger {{ color: {p.danger}; }}
    QLabel#Success {{ color: {p.success}; }}
    QLabel#Accent {{ color: {p.accent}; }}

    /* Cards and figures */
    QFrame#Card, QFrame#StatCard {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 14px;
    }}
    QFrame#Card QLabel, QFrame#StatCard QLabel {{ background: transparent; }}
    QFrame#Divider {{ background: {p.border}; max-height: 1px; border: none; }}
    QLabel#StatValue {{
        color: {p.text};
        font-family: "{mono_font}";
        font-size: 28px;
        font-weight: 500;
    }}
    QLabel#StatTitle {{
        color: {p.muted};
        font-size: 12px;
        font-weight: 400;
    }}
    QFrame#Pill {{
        background: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: 8px;
    }}
    QGroupBox {{
        background: {p.surface};
        border: 1px solid {p.border};
        border-radius: 14px;
        margin-top: 16px;
        padding: 20px 16px 16px 16px;
        font-weight: 500;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        top: 2px;
        padding: 0 6px;
        color: {p.muted};
        background: {p.surface};
        font-size: 12px;
    }}

    /* Controls */
    QPushButton {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 8px 16px;
        min-height: 22px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {p.raised}; border-color: {_mix(p.border, p.text, 0.18)}; }}
    QPushButton:pressed {{ background: {_mix(p.raised, "#000000", 0.16)}; }}
    QPushButton:disabled {{
        background: {p.surface};
        color: {_mix(p.muted, p.surface, 0.45)};
        border-color: {p.border};
    }}
    QPushButton:focus {{ border-color: {_mix(p.accent, p.border, 0.45)}; }}
    QPushButton#Primary {{
        background: {p.text};
        color: {p.bg};
        border: 1px solid {p.text};
        font-weight: 500;
    }}
    QPushButton#Primary:hover {{ background: #ffffff; border-color: #ffffff; }}
    QPushButton#Primary:pressed {{ background: {_mix(p.text, "#000000", 0.12)}; }}
    QPushButton#Primary:disabled {{
        background: {_mix(p.surface_alt, p.text, 0.18)};
        color: {_mix(p.muted, p.bg, 0.35)};
        border-color: transparent;
    }}
    QPushButton#Danger {{
        background: {p.danger_soft};
        color: {p.danger};
        border-color: {_mix(p.danger, p.border, 0.30)};
    }}
    QPushButton#Danger:hover {{ background: {_mix(p.surface, p.danger, 0.22)}; }}
    QPushButton#Success {{
        background: {p.success_soft};
        color: {p.success};
        border-color: {_mix(p.success, p.border, 0.30)};
    }}
    QPushButton#Success:hover {{ background: {_mix(p.surface, p.success, 0.22)}; }}
    QPushButton#Ghost {{ background: transparent; border-color: transparent; color: {p.muted}; }}
    QPushButton#Ghost:hover {{ background: {p.surface_alt}; color: {p.text}; }}

    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {scroll_handle};
        border-radius: 5px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {_mix(scroll_handle, p.text, 0.25)}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {scroll_handle}; border-radius: 5px; min-width: 32px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 8px 12px;
        min-height: 20px;
        selection-background-color: {p.accent};
        selection-color: {p.accent_fg};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus, QComboBox:on {{
        border-color: {_mix(p.accent, p.border, 0.45)};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
    QSpinBox:disabled, QComboBox:disabled {{ color: {p.muted}; background: {p.surface}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
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

    QSlider::groove:horizontal {{ height: 4px; background: {p.surface_alt}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
    QSlider::add-page:horizontal {{ background: {p.surface_alt}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {p.text};
        width: 14px;
        height: 14px;
        margin: -6px 0;
        border-radius: 7px;
        border: 2px solid {p.bg};
    }}
    QSlider::handle:horizontal:hover {{ background: #ffffff; }}

    QProgressBar {{
        background: {p.surface_alt};
        border: none;
        border-radius: 3px;
        min-height: 6px;
        max-height: 6px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{ background: {p.text}; border-radius: 3px; }}

    QCheckBox, QRadioButton {{ spacing: 8px; color: {p.text}; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {p.border};
        background: {p.surface_alt};
    }}
    QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}
    QCheckBox::indicator:disabled {{ background: {p.surface}; }}

    /* Data */
    QTreeWidget, QListWidget, QTableWidget {{
        background: {p.surface};
        alternate-background-color: {_mix(p.surface, p.bg, 0.28)};
        border: 1px solid {p.border};
        border-radius: 8px;
        color: {p.text};
        gridline-color: {p.border};
        selection-background-color: {selection};
        selection-color: {p.text};
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 6px 8px; border: none; }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {p.surface_alt}; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {selection};
        color: {p.text};
    }}
    QListWidget::item:selected:!active, QTreeWidget::item:selected:!active {{ background: {selection}; }}
    QHeaderView::section {{
        background: {p.surface};
        color: {p.muted};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {p.border};
        font-size: 12px;
        font-weight: 500;
    }}
    QTableCornerButton::section {{ background: {p.surface}; border: none; }}

    QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 12px; background: {p.surface}; top: -1px; }}
    QTabBar::tab {{
        background: transparent;
        color: {p.muted};
        padding: 8px 16px;
        margin-right: 2px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 400;
    }}
    QTabBar::tab:hover {{ color: {p.text}; }}
    QTabBar::tab:selected {{ color: {p.text}; border-bottom-color: {p.accent}; font-weight: 500; }}

    QMenu {{
        background: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 5px;
    }}
    QMenu::item {{ padding: 8px 20px 8px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {selection}; }}
    QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}

    QWidget#Footer {{ background: {p.sidebar}; border-top: 1px solid {p.border}; }}
    QLabel#FooterLabel {{
        color: {p.muted};
        font-family: "{mono_font}";
        font-size: 11px;
    }}
    QLabel#FooterAccent {{
        color: {p.text};
        font-family: "{mono_font}";
        font-size: 11px;
    }}

    QFrame#Toast {{
        background: {p.raised};
        border: 1px solid {p.border};
        border-radius: 10px;
    }}
    QLabel#ToastText {{ color: {p.text}; font-weight: 400; }}
    QPlainTextEdit#CodeEditor {{
        background: {p.bg};
        color: {p.text};
        font-family: "{mono_font}";
        font-size: 12px;
        border: none;
        border-radius: 0;
        padding: 8px;
    }}
    QDialogButtonBox QPushButton {{ min-width: 88px; }}
    """


def apply_theme(app: QApplication, palette: Palette) -> tuple[str, str]:
    """Install the palette, font and stylesheet on *app*."""
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
