"""PipeWire/WirePlumber and playerctl helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .commands import CommandResult, run, which

__all__ = [
    "AudioDevice",
    "NowPlaying",
    "VolumeState",
    "get_volume",
    "list_devices",
    "now_playing",
    "player_action",
    "set_default",
    "set_mute",
    "set_volume",
    "toggle_mute",
]


@dataclass(frozen=True, slots=True)
class VolumeState:
    percent: int
    muted: bool


@dataclass(frozen=True, slots=True)
class AudioDevice:
    id: str
    name: str
    driver: str
    state: str
    default: bool = False


@dataclass(frozen=True, slots=True)
class NowPlaying:
    status: str
    artist: str
    title: str

    @property
    def text(self) -> str:
        if not self.title:
            return "Nothing playing"
        if self.artist:
            return f"{self.artist} — {self.title}"
        return self.title


def _wpctl_volume(target: str) -> VolumeState | None:
    if which("wpctl") is None:
        return None
    result = run(["wpctl", "get-volume", target], timeout=5)
    if not result.ok:
        return None
    match = re.search(r"([\d.]+)", result.stdout)
    if not match:
        return None
    percent = round(float(match.group(1)) * 100)
    return VolumeState(max(0, min(150, percent)), "[MUTED]" in result.stdout.upper())


def _pactl_percent(text: str) -> int:
    match = re.search(r"(\d+)%", text)
    return int(match.group(1)) if match else 0


def get_volume(*, source: bool = False) -> VolumeState | None:
    target = "@DEFAULT_AUDIO_SOURCE@" if source else "@DEFAULT_AUDIO_SINK@"
    state = _wpctl_volume(target)
    if state is not None:
        return state
    if which("pactl") is None:
        return None
    kind = "source" if source else "sink"
    volume = run(["pactl", f"get-{kind}-volume", f"@DEFAULT_{kind.upper()}@"], timeout=5)
    mute = run(["pactl", f"get-{kind}-mute", f"@DEFAULT_{kind.upper()}@"], timeout=5)
    if not volume.ok:
        return None
    return VolumeState(
        _pactl_percent(volume.stdout),
        mute.ok and "yes" in mute.stdout.lower(),
    )


def set_volume(percent: int, *, source: bool = False) -> CommandResult:
    value = max(0, min(150, int(percent)))
    if which("wpctl"):
        target = "@DEFAULT_AUDIO_SOURCE@" if source else "@DEFAULT_AUDIO_SINK@"
        result = run(["wpctl", "set-volume", target, f"{value}%"], timeout=5)
        if result.ok:
            return result
    if which("pactl"):
        kind = "source" if source else "sink"
        return run(
            ["pactl", f"set-{kind}-volume", f"@DEFAULT_{kind.upper()}@", f"{value}%"],
            timeout=5,
        )
    return CommandResult((), 127, error="Neither wpctl nor pactl is available")


def set_mute(muted: bool, *, source: bool = False) -> CommandResult:
    if which("wpctl"):
        target = "@DEFAULT_AUDIO_SOURCE@" if source else "@DEFAULT_AUDIO_SINK@"
        result = run(["wpctl", "set-mute", target, "1" if muted else "0"], timeout=5)
        if result.ok:
            return result
    if which("pactl"):
        kind = "source" if source else "sink"
        return run(
            ["pactl", f"set-{kind}-mute", f"@DEFAULT_{kind.upper()}@", "1" if muted else "0"],
            timeout=5,
        )
    return CommandResult((), 127, error="Neither wpctl nor pactl is available")


def toggle_mute(*, source: bool = False) -> CommandResult:
    if which("wpctl"):
        target = "@DEFAULT_AUDIO_SOURCE@" if source else "@DEFAULT_AUDIO_SINK@"
        result = run(["wpctl", "set-mute", target, "toggle"], timeout=5)
        if result.ok:
            return result
    state = get_volume(source=source)
    if state is None:
        return CommandResult((), 1, error="Could not read the current mute state")
    return set_mute(not state.muted, source=source)


def _devices(kind: str) -> list[AudioDevice]:
    if which("pactl") is None:
        return []
    result = run(["pactl", "list", "short", f"{kind}s"], timeout=7)
    if not result.ok:
        return []
    default_name = ""
    default = run(["pactl", f"get-default-{kind}"], timeout=4)
    if default.ok:
        default_name = default.stdout.strip()
    devices: list[AudioDevice] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            parts = line.split()
        if len(parts) < 2:
            continue
        devices.append(
            AudioDevice(
                id=parts[0],
                name=parts[1],
                driver=parts[2] if len(parts) > 2 else "",
                state=parts[-1] if len(parts) > 3 else "",
                default=parts[1] == default_name,
            )
        )
    return devices


def list_devices() -> dict[str, list[AudioDevice]]:
    return {"sinks": _devices("sink"), "sources": _devices("source")}


def set_default(name: str, *, source: bool = False) -> CommandResult:
    if which("pactl") is None:
        return CommandResult((), 127, error="pactl is not installed")
    kind = "source" if source else "sink"
    return run(["pactl", f"set-default-{kind}", name], timeout=6)


def now_playing() -> NowPlaying | None:
    if which("playerctl") is None:
        return None
    title = run(["playerctl", "metadata", "title"], timeout=4)
    if not title.ok or not title.stdout.strip():
        return None
    artist = run(["playerctl", "metadata", "artist"], timeout=4)
    status = run(["playerctl", "status"], timeout=4)
    return NowPlaying(
        status=status.stdout.strip() if status.ok else "",
        artist=artist.stdout.strip() if artist.ok else "",
        title=title.stdout.strip(),
    )


def player_action(action: str) -> CommandResult:
    if action not in {"play-pause", "next", "previous", "stop", "play", "pause"}:
        return CommandResult((), 2, error=f"Unsupported player action: {action}")
    if which("playerctl") is None:
        return CommandResult((), 127, error="playerctl is not installed")
    return run(["playerctl", action], timeout=6)
