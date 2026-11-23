from __future__ import annotations

from pathlib import Path

from control_panel.core.hyprland import (
    config_files,
    config_lines,
    monitor_lines,
    update_lines,
)


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "hypr"
    root.mkdir()
    (root / "main.conf").write_text(
        "source = ./modules/colors.conf\n"
        "source = ./modules/extra.conf\n"
        "source = ~/not-expanded-in-tests.conf\n"
        "monitor=eDP-1,1920x1080@144,0x0,1\n"
        "general {\n"
        "    gaps_in = 7\n"
        "}\n"
    )
    modules = root / "modules"
    modules.mkdir()
    (modules / "colors.conf").write_text("$accent = rgb(cbe69a)\n")
    (modules / "extra.conf").write_text("source = ../main.conf\n")
    return root / "main.conf"


def test_config_files_follows_sources(tmp_path: Path) -> None:
    main = _tree(tmp_path)
    files = config_files(main)
    assert [path.name for path in files] == ["main.conf", "colors.conf", "extra.conf"]


def test_config_lines_and_monitors(tmp_path: Path) -> None:
    main = _tree(tmp_path)
    lines = monitor_lines(root=main)
    assert len(lines) == 1
    assert lines[0].text.startswith("monitor=eDP-1")
    gaps = config_lines("general:gaps_in", root=main)
    assert gaps == []
    assert len(config_lines("source", root=main)) == 4


def test_update_lines_creates_backup(tmp_path: Path) -> None:
    main = _tree(tmp_path)
    entries = monitor_lines(root=main)[0]
    ok, error = update_lines({entries.path: {entries.index: "monitor=eDP-1,2560x1440@165,0x0,1"}})
    assert ok, error
    assert "2560x1440" in main.read_text()
    assert main.with_name("main.conf.bak").is_file()
