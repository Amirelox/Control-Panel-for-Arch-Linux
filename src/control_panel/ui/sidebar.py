"""Collapsible navigation sidebar."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
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

EXPANDED_WIDTH = 240
COLLAPSED_WIDTH = 64


@dataclass(frozen=True, slots=True)
class NavItem:
    label: str


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
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.logo = QLabel("Control Panel")
        self.logo.setObjectName("Logo")
        header.addWidget(self.logo)
        header.addStretch()
        self.toggle_btn = QPushButton("<<")
        self.toggle_btn.setObjectName("Ghost")
        self.toggle_btn.setFixedSize(34, 32)
        self.toggle_btn.setStyleSheet("padding: 0;")
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.toggle_btn.clicked.connect(self.toggle)
        header.addWidget(self.toggle_btn)
        layout.addLayout(header)
        self.subtitle = QLabel("Arch Linux · Hyprland")
        self.subtitle.setObjectName("AppSubtitle")
        layout.addWidget(self.subtitle)
        layout.addSpacing(12)
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(12)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, item in enumerate(items):
            button = QPushButton(item.label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setToolTip(item.label)
            button.setAccessibleName(item.label)
            button.clicked.connect(lambda _checked=False, i=index: self.page_selected.emit(i))
            self.group.addButton(button, index)
            layout.addWidget(button)
            self._buttons.append(button)
        layout.addStretch()

        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.version = QLabel(f"v{VERSION}")
        self.version.setObjectName("MonoHint")
        footer.addWidget(self.version)
        footer.addStretch()
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("Ghost")
        self.settings_btn.setFixedHeight(28)
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
        self.logo.setText("Control Panel")
        self.logo.setVisible(not collapsed)
        self.subtitle.setVisible(not collapsed)
        self.version.setVisible(not collapsed)
        self.settings_btn.setText("Prefs" if collapsed else "Settings")
        self.settings_btn.setStyleSheet("padding: 0;" if collapsed else "")
        self.toggle_btn.setText(">>" if collapsed else "<<")
        self.toggle_btn.setToolTip("Expand sidebar" if collapsed else "Collapse sidebar")
        for index, (button, item) in enumerate(zip(self._buttons, self._items, strict=False)):
            button.setText(f"{index + 1:02d}" if collapsed else item.label)
            button.setToolTip(item.label)
            if collapsed:
                button.setStyleSheet("text-align: center; padding-left: 0; padding-right: 0;")
            else:
                button.setStyleSheet("")
        if emit:
            self.collapsed_changed.emit(collapsed)
