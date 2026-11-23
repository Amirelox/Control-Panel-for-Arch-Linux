from __future__ import annotations

from pathlib import Path

from control_panel.core.storage import scan_large_files


def test_scan_large_files(tmp_path: Path) -> None:
    (tmp_path / "small.txt").write_text("x")
    (tmp_path / "large.bin").write_bytes(b"x" * 2048)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "medium.bin").write_bytes(b"y" * 1024)
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "huge.bin").write_bytes(b"z" * 9999)

    results, scanned, truncated = scan_large_files(tmp_path, limit=2)
    assert [path.name for _size, path in results] == ["large.bin", "medium.bin"]
    assert scanned == 3
    assert truncated is False


def test_scan_large_files_cancel(tmp_path: Path) -> None:
    for index in range(10):
        (tmp_path / f"file-{index}").write_text("x")
    results, _scanned, _truncated = scan_large_files(tmp_path, limit=5, should_stop=lambda: True)
    assert results == []
