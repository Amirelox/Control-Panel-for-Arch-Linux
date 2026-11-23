"""Reusable Qt widgets used by every page."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QTextFormat,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.commands import CommandResult, CommandRunner
from ..core.config import Settings
from ..core.parsers import format_bytes

__all__ = [
    "ActivityChart",
    "BasePage",
    "Card",
    "CodeEditor",
    "DataTable",
    "EmptyState",
    "FlowLayout",
    "HLine",
    "KeyValueGrid",
    "ProgressRow",
    "SearchField",
    "Sparkline",
    "StatCard",
    "ToastManager",
    "TwoColumn",
    "ask",
    "ask_text",
    "theme_icon",
]


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
class FlowLayout(QLayout):
    """A layout that wraps its children like text, used for stat cards."""

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 12) -> None:
        super().__init__(parent)
        self._items: list[Any] = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


def HLine() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Divider")
    frame.setFrameShape(QFrame.Shape.HLine)
    frame.setFixedHeight(1)
    return frame


def theme_icon(name: str, fallback: QStyle.StandardPixmap | None = None) -> QIcon:
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        return icon
    if fallback is not None:
        return QApplication.style().standardIcon(fallback)
    return QIcon()


class SearchField(QLineEdit):
    def __init__(self, placeholder: str = "Search", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        icon = theme_icon("system-search", QStyle.StandardPixmap.SP_FileDialogContentsView)
        if not icon.isNull():
            self.addAction(icon, QLineEdit.ActionPosition.LeadingPosition)
        self.setMinimumHeight(34)


class DataTable(QTreeWidget):
    def __init__(
        self,
        columns: Sequence[str],
        *,
        stretch_column: int = -1,
        min_height: int = 200,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setColumnCount(len(columns))
        self.setHeaderLabels(list(columns))
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setMinimumHeight(min_height)
        self.setAllColumnsShowFocus(True)
        header = self.header()
        header.setStretchLastSection(stretch_column < 0 or stretch_column >= len(columns))
        for index in range(len(columns)):
            header.setSectionResizeMode(
                index,
                QHeaderView.ResizeMode.Stretch
                if index == stretch_column
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._mono_columns: dict[int, bool] = {}
        self._mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._mono_font.setPointSizeF(9.5)

    def set_mono_columns(self, *columns: int, right: bool = True) -> None:
        for column in columns:
            self._mono_columns[column] = right
        self._apply_mono()

    def addTopLevelItem(self, item) -> None:
        super().addTopLevelItem(item)
        for column, right in self._mono_columns.items():
            item.setFont(column, self._mono_font)
            if right:
                item.setTextAlignment(
                    column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )

    def _apply_mono(self) -> None:
        for index in range(self.topLevelItemCount()):
            item = self.topLevelItem(index)
            for column, right in self._mono_columns.items():
                item.setFont(column, self._mono_font)
                if right:
                    item.setTextAlignment(
                        column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )

    def fit_rows(self, *, max_rows: int = 10, empty_height: int = 128) -> None:
        count = self.topLevelItemCount()
        if count == 0:
            self.setFixedHeight(empty_height)
            return
        row_height = self.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 30
        header_height = max(30, self.header().height())
        height = header_height + row_height * min(count, max_rows) + 8
        self.setFixedHeight(max(empty_height, height))

    def selected_text(self, column: int = 0) -> str | None:
        item = self.currentItem()
        if item is None:
            return None
        value = item.text(column)
        return value or None

    def clear_rows(self) -> None:
        self.setSortingEnabled(False)
        self.clear()
        self.setSortingEnabled(True)


class KeyValueGrid(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(16)
        self._layout.setVerticalSpacing(8)
        self._layout.setColumnStretch(1, 1)
        self._values: dict[str, QLabel] = {}
        self._row = 0

    def add(self, key: str, value: str = "…") -> QLabel:
        key_label = QLabel(key)
        key_label.setObjectName("Muted")
        key_label.setMinimumWidth(110)
        value_label = QLabel(value)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)
        self._layout.addWidget(key_label, self._row, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(value_label, self._row, 1, Qt.AlignmentFlag.AlignTop)
        self._values[key] = value_label
        self._row += 1
        return value_label

    def set(self, key: str, value: str) -> None:
        label = self._values.get(key)
        if label is not None:
            label.setText(value or "—")

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._values.clear()
        self._row = 0

    @property
    def row_count(self) -> int:
        return len(self._values)

    def add_stretch(self) -> None:
        self._layout.setRowStretch(self._row, 1)


class StatCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "—",
        subtitle: str = "",
        *,
        minimum_width: int = 160,
    ) -> None:
        super().__init__()
        self.setObjectName("StatCard")
        self.setMinimumWidth(minimum_width)
        self.setMinimumHeight(108)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("StatTitle")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.value_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Hint")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)
        layout.addStretch()

    def set_value(self, value: str, subtitle: str | None = None) -> None:
        self.value_label.setText(value)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)
            self.subtitle_label.setVisible(bool(subtitle))


class Card(QFrame):
    def __init__(self, title: str = "", *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.title_label.setVisible(bool(title))
        self.header.addWidget(self.title_label)
        self.header.addStretch()
        outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        outer.addLayout(self.body)

    def add(self, widget: QWidget) -> QWidget:
        if isinstance(widget, QPushButton) and widget.objectName() in {
            "Primary",
            "Danger",
            "Success",
        }:
            widget.setMaximumWidth(280)
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout: QLayout) -> QLayout:
        self.body.addLayout(layout)
        return layout

    def add_action(self, widget: QWidget) -> QWidget:
        self.header.addWidget(widget)
        return widget


class ProgressRow(QWidget):
    def __init__(
        self,
        label: str,
        *,
        label_width: int = 90,
        value_width: int = 150,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.label = QLabel(label)
        self.label.setObjectName("Muted")
        self.label.setFixedWidth(label_width)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.value = QLabel("—")
        self.value.setObjectName("MonoHint")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value.setMinimumWidth(value_width)
        layout.addWidget(self.label)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.value)

    def set(self, percent: float, text: str | None = None) -> None:
        value = int(max(0, min(100, round(percent))))
        self.bar.setValue(value)
        if text is not None:
            self.value.setText(text)


class Sparkline(QWidget):
    """Compact throughput chart without decoration."""

    def __init__(
        self,
        samples: int = 80,
        parent: QWidget | None = None,
        *,
        ceiling: float = 0.0,
    ) -> None:
        super().__init__(parent)
        self._values: deque[float] = deque(maxlen=samples)
        self._colour = QColor("#d6a45f")
        self._border = QColor("#2c2d33")
        self._ceiling = max(0.0, ceiling)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_colour(self, colour: str) -> None:
        self._colour = QColor(colour)
        self.update()

    def set_border(self, colour: str) -> None:
        self._border = QColor(colour)
        self.update()

    def append(self, value: float) -> None:
        self._values.append(max(0.0, float(value)))
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 6, 0, -6)
        if rect.width() <= 2 or rect.height() <= 2:
            return
        painter.setPen(QPen(self._border, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if len(self._values) < 2:
            return

        values = list(self._values)
        peak = max(max(values), self._ceiling, 1.0)
        step = rect.width() / max(1, len(values) - 1)
        points = [
            (rect.left() + index * step, rect.bottom() - (value / peak) * rect.height())
            for index, value in enumerate(values)
        ]
        path = QPainterPath()
        path.moveTo(points[0][0], points[0][1])
        for x, y in points[1:]:
            path.lineTo(x, y)
        painter.setPen(QPen(self._colour, 1.6))
        painter.drawPath(path)


class ActivityChart(QWidget):
    """A small, deliberate CPU/memory history chart."""

    def __init__(self, samples: int = 60, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cpu: deque[float] = deque(maxlen=samples)
        self._memory: deque[float] = deque(maxlen=samples)
        self._accent = QColor("#d6a45f")
        self._muted = QColor("#989ba4")
        self._border = QColor("#2c2d33")
        self._mono_font = "Monospace"
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def configure(self, palette, mono_font: str) -> None:
        self._accent = QColor(palette.accent)
        self._muted = QColor(palette.muted)
        self._border = QColor(palette.border)
        self._mono_font = mono_font
        self.update()

    def append(self, cpu: float, memory: float) -> None:
        self._cpu.append(max(0.0, min(100.0, cpu)))
        self._memory.append(max(0.0, min(100.0, memory)))
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont(self._mono_font, 9))
        metrics = painter.fontMetrics()
        left = 46
        top = 30
        right = self.width() - 12
        bottom = self.height() - 24
        if right - left < 20 or bottom - top < 20:
            return

        grid = QPen(self._border, 1)
        for index, value in enumerate((100, 50, 0)):
            y = int(top + (bottom - top) * index / 2)
            painter.setPen(grid)
            painter.drawLine(left, y, right, y)
            painter.setPen(self._muted)
            painter.drawText(
                0,
                int(y - metrics.height() / 2 + 1),
                left - 8,
                metrics.height(),
                Qt.AlignmentFlag.AlignRight,
                f"{value}%",
            )

        legend_y = 8
        painter.setPen(QPen(self._accent, 2))
        painter.drawLine(left, legend_y + 7, left + 16, legend_y + 7)
        painter.setPen(self._muted)
        painter.drawText(left + 22, legend_y + 11, "CPU")
        painter.setPen(QPen(self._muted, 2))
        painter.drawLine(left + 64, legend_y + 7, left + 80, legend_y + 7)
        painter.drawText(left + 86, legend_y + 11, "Memory")

        if len(self._cpu) < 2:
            painter.setPen(self._muted)
            painter.drawText(
                left,
                top,
                right - left,
                bottom - top,
                Qt.AlignmentFlag.AlignCenter,
                "Collecting samples…",
            )
            return

        def points(series: deque[float]) -> list[tuple[float, float]]:
            step = (right - left) / max(1, len(series) - 1)
            return [
                (left + index * step, bottom - (value / 100.0) * (bottom - top))
                for index, value in enumerate(series)
            ]

        for series, colour, width in (
            (self._memory, self._muted, 1.2),
            (self._cpu, self._accent, 1.8),
        ):
            values = points(series)
            path = QPainterPath()
            path.moveTo(values[0][0], values[0][1])
            for x, y in values[1:]:
                path.lineTo(x, y)
            painter.setPen(QPen(colour, width))
            painter.drawPath(path)

        painter.setPen(self._muted)
        painter.drawText(
            left,
            self.height() - 16,
            right - left,
            metrics.height(),
            Qt.AlignmentFlag.AlignRight,
            "60 s",
        )


class TwoColumn(QWidget):
    """Two cards side by side, stacked when the window gets narrow."""

    def __init__(
        self,
        left: QWidget,
        right: QWidget,
        *,
        breakpoint: int = 840,
        left_stretch: int = 2,
        right_stretch: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._left = left
        self._right = right
        self._breakpoint = breakpoint
        self._left_stretch = left_stretch
        self._right_stretch = right_stretch
        self._stacked: bool | None = None
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        self._apply(force=True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()

    def _apply(self, *, force: bool = False) -> None:
        stacked = self.width() < self._breakpoint
        if not force and stacked == self._stacked:
            return
        self._stacked = stacked
        self._grid.removeWidget(self._left)
        self._grid.removeWidget(self._right)
        self._grid.addWidget(self._left, 0, 0)
        if stacked:
            self._grid.addWidget(self._right, 1, 0)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)
        else:
            self._grid.addWidget(self._right, 0, 1)
            self._grid.setColumnStretch(0, self._left_stretch)
            self._grid.setColumnStretch(1, self._right_stretch)


class EmptyState(QWidget):
    def __init__(self, title: str, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 26, 12, 26)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: 500;")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)
        if text:
            detail = QLabel(text)
            detail.setObjectName("Muted")
            detail.setWordWrap(True)
            detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(detail)


# ---------------------------------------------------------------------------
# Code editor with line numbers
# ---------------------------------------------------------------------------
class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None, *, mono_font: str = "Monospace") -> None:
        super().__init__(parent)
        self.setObjectName("CodeEditor")
        self.setFont(QFont(mono_font, 11))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_area_width()
        self._highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents = self.contentsRect()
        self._line_area.setGeometry(
            QRect(contents.left(), contents.top(), self.line_number_area_width(), contents.height())
        )

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 0))
        painter.setPen(QColor("#6f727a"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0,
                    top,
                    self._line_area.width() - 7,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    def _highlight_current_line(self) -> None:
        if self.isReadOnly():
            self.setExtraSelections([])
            return
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(255, 255, 255, 8))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            cursor = self.textCursor()
            cursor.insertText("    ")
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Dialogs and toasts
# ---------------------------------------------------------------------------
def ask(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    danger: bool = False,
    ok_text: str = "Continue",
) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    confirm = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is confirm


def ask_text(
    parent: QWidget | None,
    title: str,
    label: str,
    *,
    password: bool = False,
) -> str | None:
    from PyQt6.QtWidgets import QInputDialog

    echo = QLineEdit.EchoMode.Password if password else QLineEdit.EchoMode.Normal
    text, accepted = QInputDialog.getText(parent, title, label, echo)
    return text if accepted else None


class Toast(QFrame):
    def __init__(self, text: str, level: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setMaximumWidth(460)
        self.setMinimumWidth(240)
        colours = {
            "info": "#8aa9c9",
            "success": "#83bd91",
            "warning": "#d6a45f",
            "error": "#d97b7b",
        }
        colour = colours.get(level, colours["info"])
        self.setStyleSheet(f"QFrame#Toast {{ border-left: 3px solid {colour}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 16, 12)
        layout.setSpacing(10)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {colour}; font-size: 12px;")
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setObjectName("ToastText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label, 1)
        self.adjustSize()
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)


class ToastManager:
    """Small non-blocking notification stack in the corner of the window."""

    def __init__(self, parent: QWidget) -> None:
        self._parent = parent
        self._toasts: list[Toast] = []
        self._animations: list[QPropertyAnimation] = []

    def show(self, text: str, level: str = "info", timeout_ms: int = 3800) -> None:
        if not text:
            return
        while len(self._toasts) >= 3:
            self._dismiss(self._toasts[0])
        toast = Toast(text, level, self._parent)
        toast.show()
        toast.raise_()
        self._toasts.append(toast)
        self._restack()

        animation = QPropertyAnimation(toast._effect, b"opacity", toast)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._animations.append(animation)
        animation.finished.connect(lambda: self._forget(animation))

        QTimer.singleShot(timeout_ms, lambda: self._fade_out(toast))

    def _fade_out(self, toast: Toast) -> None:
        if toast not in self._toasts:
            return
        animation = QPropertyAnimation(toast._effect, b"opacity", toast)
        animation.setDuration(240)
        animation.setStartValue(toast._effect.opacity())
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InCubic)
        animation.finished.connect(lambda: self._dismiss(toast))
        animation.start()
        self._animations.append(animation)

    def _dismiss(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.hide()
        toast.deleteLater()
        self._restack()

    def _forget(self, animation: QPropertyAnimation) -> None:
        if animation in self._animations:
            self._animations.remove(animation)

    def _restack(self) -> None:
        area = self._parent.rect()
        margin = 22
        bottom = area.bottom() - margin
        for toast in reversed(self._toasts):
            toast.adjustSize()
            width = min(toast.sizeHint().width(), 460)
            height = toast.sizeHint().height()
            toast.setFixedWidth(width)
            x = area.right() - margin - width
            toast.move(max(margin, x), max(margin, bottom - height))
            bottom -= height + 8

    def reposition(self) -> None:
        self._restack()


# ---------------------------------------------------------------------------
# Page base class
# ---------------------------------------------------------------------------
class BasePage(QWidget):
    """Common page frame: header, scroll area and safe async helpers."""

    title: str = ""
    subtitle: str = ""
    icon_name: str = ""
    fallback_icon: QStyle.StandardPixmap | None = None

    def __init__(
        self,
        runner: CommandRunner,
        settings: Settings,
        *,
        mono_font: str = "Monospace",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.runner = runner
        self.settings = settings
        self.mono_font = mono_font
        self._alive = True
        self.setObjectName("Page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 20, 32, 16)
        outer.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.eyebrow = QLabel("")
        self.eyebrow.setObjectName("PageEyebrow")
        self.eyebrow.setVisible(False)
        titles.addWidget(self.eyebrow)
        title_label = QLabel(self.title)
        title_label.setObjectName("PageTitle")
        titles.addWidget(title_label)
        if self.subtitle:
            subtitle_label = QLabel(self.subtitle)
            subtitle_label.setObjectName("PageSubtitle")
            subtitle_label.setWordWrap(True)
            titles.addWidget(subtitle_label)
        header.addLayout(titles, 1)
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(8)
        header.addLayout(self.header_actions)
        outer.addLayout(header)
        outer.addWidget(HLine())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("PageContent")
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 4, 10, 24)
        self.body.setSpacing(20)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

    def set_page_index(self, index: int, total: int) -> None:
        self.eyebrow.setText(f"{index:02d} / {total:02d}")
        self.eyebrow.setVisible(True)

    # -- layout helpers -----------------------------------------------------
    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_section(self, text: str, action: QWidget | None = None) -> QLabel:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        layout.addStretch()
        if action is not None:
            layout.addWidget(action)
        self.body.addWidget(row)
        return label

    def add_row(self, *widgets: QWidget, spacing: int = 8) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(spacing)
        for widget in widgets:
            row.addWidget(widget)
        row.addStretch()
        self.body.addLayout(row)
        return row

    def add_card(self, title: str = "") -> Card:
        card = Card(title)
        self.body.addWidget(card)
        return card

    def add_stretch(self) -> None:
        self.body.addStretch()

    def add_flow(self, widgets: Iterable[QWidget], spacing: int = 16) -> FlowLayout:
        holder = QWidget()
        flow = FlowLayout(holder, spacing=spacing)
        for widget in widgets:
            flow.addWidget(widget)
        self.body.addWidget(holder)
        return flow

    def add_action_button(
        self,
        text: str,
        callback: Callable[[], None],
        *,
        icon: str = "",
        style: str = "",
        tooltip: str = "",
    ) -> QPushButton:
        button = QPushButton(text)
        if style:
            button.setObjectName(style)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(lambda: callback())
        self.header_actions.addWidget(button)
        return button

    # -- notifications ------------------------------------------------------
    def notify(self, message: str, level: str = "info", timeout_ms: int = 3800) -> None:
        window = self.window()
        show = getattr(window, "notify", None)
        if callable(show):
            show(message, level, timeout_ms)

    def confirm(
        self,
        title: str,
        text: str,
        *,
        danger: bool = False,
        ok_text: str = "Continue",
    ) -> bool:
        if self.settings.confirm_destructive:
            return ask(self.window(), title, text, danger=danger, ok_text=ok_text)
        return True

    # -- jobs ---------------------------------------------------------------
    def call(
        self,
        function: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        def guarded(value: Any) -> None:
            if self._alive and on_done is not None:
                on_done(value)

        def failed(message: str, trace: str) -> None:
            if self._alive:
                if on_error is not None:
                    on_error(message, trace)
                else:
                    self.notify(message, "error")

        self.runner.submit(function, on_done=guarded, on_error=failed)

    def run_command(
        self,
        argv: Sequence[str],
        on_done: Callable[[CommandResult], None] | None = None,
        *,
        timeout: float = 15.0,
        busy: QPushButton | None = None,
        busy_text: str = "Working…",
        report_errors: bool = True,
    ) -> None:
        if busy is not None:
            self._set_busy(busy, True, busy_text)

        def guarded(result: CommandResult) -> None:
            if busy is not None:
                self._set_busy(busy, False)
            if not self._alive:
                return
            if report_errors and not result.ok:
                self.notify(result.summary(), "error")
            if on_done is not None:
                on_done(result)

        self.runner.run(argv, guarded, timeout=timeout)

    @staticmethod
    def _set_busy(button: QPushButton, busy: bool, text: str = "") -> None:
        if busy:
            button.setProperty("acc_old_text", button.text())
            button.setText(text)
            button.setEnabled(False)
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            old = button.property("acc_old_text")
            if isinstance(old, str) and old:
                button.setText(old)
            button.setEnabled(True)
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

    # -- lifecycle ----------------------------------------------------------
    def on_show(self) -> None:
        """Called every time the page becomes visible."""

    def on_hide(self) -> None:
        """Called when another page is selected."""

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.on_show()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.on_hide()

    def shutdown(self) -> None:
        self._alive = False


# Small helper used by some pages.
def bytes_label(value: float | int) -> str:
    return format_bytes(value)
