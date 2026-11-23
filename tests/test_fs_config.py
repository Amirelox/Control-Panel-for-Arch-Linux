from __future__ import annotations

import json
from pathlib import Path

from control_panel.core.config import Settings, SettingsStore
from control_panel.core.fs import (
    backup_file,
    directory_size,
    is_under,
    read_text,
    remove_directory_contents,
    write_text_atomic,
)


def test_atomic_write_and_backup(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.conf"
    write_text_atomic(target, "one\n")
    assert target.read_text() == "one\n"
    assert backup_file(target) == target.with_name("file.conf.bak")
    write_text_atomic(target, "two\n")
    assert target.read_text() == "two\n"
    assert target.with_name("file.conf.bak").read_text() == "one\n"
    assert not list(tmp_path.rglob("*.tmp"))


def test_read_text_missing(tmp_path: Path) -> None:
    assert read_text(tmp_path / "missing", "fallback") == "fallback"


def test_is_under(tmp_path: Path) -> None:
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert is_under(child, tmp_path)
    assert not is_under(tmp_path, child)


def test_remove_directory_contents(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "one.tmp").write_text("x" * 10)
    nested = cache / "nested"
    nested.mkdir()
    (nested / "two.tmp").write_text("y" * 20)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    (cache / "link").symlink_to(outside)
    files, size = remove_directory_contents(cache)
    assert files == 3
    assert size >= 30
    assert cache.is_dir()
    assert outside.read_text() == "keep"
    assert list(cache.iterdir()) == []


def test_directory_size(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("1234")
    nested = tmp_path / "n"
    nested.mkdir()
    (nested / "b").write_text("123456")
    assert directory_size(tmp_path) == 10


def test_settings_defaults(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = store.load()
    assert settings.refresh_ms == 1000
    assert settings.confirm_destructive is True
    assert settings.last_page == 0


def test_settings_roundtrip_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "refresh_ms": 5,
                "last_page": -2,
                "scan_limit": 1,
                "accent": "bogus",
                "hide_sensitive_env": "yes",
                "unknown": 1,
            }
        )
    )
    settings = SettingsStore(path).load()
    assert settings.refresh_ms == 500
    assert settings.last_page == 0
    assert settings.scan_limit == 10_000
    assert settings.accent == "auto"
    assert settings.hide_sensitive_env is True

    store = SettingsStore(path)
    store.save(settings)
    again = store.load()
    assert again == settings


def test_settings_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert SettingsStore(path).load() == Settings()
