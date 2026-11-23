from __future__ import annotations

from control_panel.ui.theme import _mix, _normalise_hex, load_palette


def test_hyprland_color_forms() -> None:
    assert _normalise_hex("rgb(cbe69a)") == "#cbe69a"
    assert _normalise_hex("rgba(cbe69aff)") == "#cbe69a"
    assert _normalise_hex("#CBE69A") == "#cbe69a"
    assert _normalise_hex("#cbe69aff") == "#cbe69a"
    assert _normalise_hex("0xffcbe69a") == "#cbe69a"
    assert _normalise_hex("not-a-colour") is None


def test_mix_and_palette() -> None:
    assert _mix("#000000", "#ffffff", 0.5) == "#808080"
    palette = load_palette("violet")
    assert palette.accent == "#d9b8ff"
    assert palette.bg.startswith("#")
    assert palette.accent_fg.startswith("#")
