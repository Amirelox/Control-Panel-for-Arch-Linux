"""Collapsible navigation sidebar."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.config import VERSION
from .widgets import theme_icon

EXPANDED_WIDTH = 224
COLLAPSED_WIDTH = 68


@dataclass(frozen=True, slots=True)
class NavItem:
    label: str
    icon: str
    fallback: object = None


class Sidebar(QWidget):
    page_selected = pyqtSignal(int)
    collapsed_changed = pyqtSignal(bool)
    toggled_by_user = pyqtSignal(bool)
    settings_requested = pyqtSignal()

    def __init__(self, items: list[NavItem], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._items = items
        self._collapsed = False
        self._buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(4)
        self.logo = QLabel("Control Panel")
        self.logo.setObjectName("Logo")
        header.addWidget(self.logo)
        header.addStretch()
        self.toggle_btn = QPushButton("<")
        self.toggle_btn.setObjectName("Ghost")
        self.toggle_btn.setFixedSize(28, 28)
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.toggle_btn.clicked.connect(self.toggle)
        header.addWidget(self.toggle_btn)
        layout.addLayout(header)
        self.subtitle = QLabel("Arch Linux · Hyprland")
        self.subtitle.setObjectName("AppSubtitle")
        layout.addWidget(self.subtitle)
        layout.addSpacing(8)
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(8)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, item in enumerate(items):
            button = QPushButton(item.label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setIcon(theme_icon(item.icon, item.fallback))
            button.setIconSize(QSize(18, 18))
            button.setToolTip(item.label)
            button.setAccessibleName(item.label)
            button.clicked.connect(lambda _checked=False, i=index: self.page_selected.emit(i))
            self.group.addButton(button, index)
            layout.addWidget(button)
            self._buttons.append(button)
        layout.addStretch()

        footer = QHBoxLayout()
        footer.setSpacing(2)
        self.version = QLabel(f"v{VERSION}")
        self.version.setObjectName("Hint")
        footer.addWidget(self.version)
        footer.addStretch()
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("Ghost")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setToolTip("Preferences (Ctrl+,)")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        footer.addWidget(self.settings_btn)
        layout.addLayout(footer)
        self.set_collapsed(False, emit=False)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle(self) -> None:
        collapsed = not self._collapsed
        self.set_collapsed(collapsed)
        self.toggled_by_user.emit(collapsed)

    def set_collapsed(self, collapsed: bool, *, emit: bool = True) -> None:
        if collapsed == self._collapsed and emit:
            return
        self._collapsed = collapsed
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH)
        self.logo.setText("CP" if collapsed else "Control Panel")
        self.logo.setObjectName("LogoCompact" if collapsed else "Logo")
        self.logo.style().unpolish(self.logo)
        self.logo.style().polish(self.logo)
        self.subtitle.setVisible(not collapsed)
        self.version.setVisible(not collapsed)
        self.settings_btn.setText("⚙")
        self.toggle_btn.setText(">" if collapsed else "<")
        self.toggle_btn.setToolTip("Expand sidebar" if collapsed else "Collapse sidebar")
        for button, item in zip(self._buttons, self._items, strict=False):
            button.setText("" if collapsed else item.label)
            button.setToolTip(item.label)
            if collapsed:
                button.setStyleSheet("text-align: center; padding-left: 0; padding-right: 0;")
            else:
                button.setStyleSheet("")
        if emit:
            self.collapsed_changed.emit(collapsed)
