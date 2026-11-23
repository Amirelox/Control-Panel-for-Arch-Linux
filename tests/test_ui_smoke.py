from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QStyle, QWidget

from control_panel.core.commands import CommandRunner
from control_panel.core.config import Settings, SettingsStore
from control_panel.ui import main_window as main_window_module
from control_panel.ui.main_window import MainWindow, PageSpec
from control_panel.ui.theme import load_palette
from control_panel.ui.widgets import StatCard


class DummyPage(QWidget):
    def __init__(self, runner, settings, *, palette=None, mono_font="Monospace", parent=None):
        super().__init__(parent)
        self.stats = 0
        self._alive = True

    def update_stats(self, stats) -> None:
        self.stats += 1

    def refresh(self) -> None:
        pass

    def shutdown(self) -> None:
        self._alive = False


def test_main_window_smoke(qtbot, tmp_path: Path, monkeypatch) -> None:
    specs = [
        PageSpec("One", "computer-symbolic", QStyle.StandardPixmap.SP_ComputerIcon, DummyPage),
        PageSpec("Two", "network-wireless", QStyle.StandardPixmap.SP_DriveNetIcon, DummyPage),
    ]
    monkeypatch.setattr(main_window_module, "PAGE_SPECS", specs)

    settings = Settings(last_page=0, refresh_ms=500)
    store = SettingsStore(tmp_path / "settings.json")
    runner = CommandRunner(max_threads=2)
    window = MainWindow(store, settings, runner, load_palette("violet"))
    qtbot.addWidget(window)
    window.show()
    window.switch_page(0)
    qtbot.wait(50)

    assert window.stack.currentWidget() is not None
    assert window.panel_errors == 0
    assert window.sidebar.is_collapsed() is False

    window.resize(800, 600)
    qtbot.wait(50)
    assert window.sidebar.is_collapsed() is True
    window.resize(1300, 800)
    qtbot.wait(50)
    assert window.sidebar.is_collapsed() is False

    window.switch_page(1)
    assert settings.last_page == 1
    window.sidebar.toggle()
    assert window.sidebar.is_collapsed() is True
    window.close()
    assert (tmp_path / "settings.json").is_file()


def test_stat_card_flow(qtbot) -> None:
    cards = [StatCard("CPU", "12%"), StatCard("RAM", "34%"), StatCard("Disk", "56%")]
    for card in cards:
        qtbot.addWidget(card)
        card.show()
    qtbot.wait(30)
    for card in cards:
        assert card.value_label.text() in {"12%", "34%", "56%"}
