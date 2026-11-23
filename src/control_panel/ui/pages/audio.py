"""Audio page: PipeWire volume, devices and media controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QTreeWidgetItem,
    QWidget,
)

from ...core import audio
from ...core.commands import CommandRunner
from ...core.config import Settings
from ..widgets import BasePage, Card, DataTable


class AudioPage(BasePage):
    title = "Audio"
    subtitle = "PipeWire volume, microphones and media playback"
    icon_name = "audio-volume-high-symbolic"
    fallback_icon = QStyle.StandardPixmap.SP_MediaVolume

    def __init__(
        self,
        runner: CommandRunner,
        settings: Settings,
        *,
        mono_font: str = "Monospace",
        palette=None,
        parent=None,
    ) -> None:
        super().__init__(runner, settings, mono_font=mono_font, parent=parent)
        self._loaded = False
        self._volume_timer = QTimer(self)
        self._volume_timer.setSingleShot(True)
        self._volume_timer.setInterval(120)
        self._volume_timer.timeout.connect(self._apply_volume)
        self._mic_timer = QTimer(self)
        self._mic_timer.setSingleShot(True)
        self._mic_timer.setInterval(120)
        self._mic_timer.timeout.connect(self._apply_mic)
        self._np_busy = False

        self.add_action_button(
            "Refresh",
            self.refresh,
            icon="view-refresh",
            style="Ghost",
            tooltip="Reload volume and device information",
        )

        # Output volume --------------------------------------------------
        self.add_section("Output")
        output = Card("Master volume")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setEnabled(False)
        self.volume_slider.valueChanged.connect(self._volume_changed)
        self.volume_value = QLabel("—%")
        self.volume_value.setMinimumWidth(48)
        self.volume_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.mute_btn = QPushButton("Mute")
        self.mute_btn.clicked.connect(self.toggle_mute)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Quiet"))
        row.addWidget(self.volume_slider, 1)
        row.addWidget(QLabel("Loud"))
        row.addWidget(self.volume_value)
        row.addWidget(self.mute_btn)
        holder = QWidget()
        holder.setLayout(row)
        output.add(holder)
        self.output_hint = QLabel("")
        self.output_hint.setObjectName("Hint")
        output.add(self.output_hint)
        self.add(output)

        # Microphone -----------------------------------------------------
        self.add_section("Input")
        microphone = Card("Microphone")
        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(0, 100)
        self.mic_slider.setEnabled(False)
        self.mic_slider.valueChanged.connect(self._mic_changed)
        self.mic_value = QLabel("—%")
        self.mic_value.setMinimumWidth(48)
        self.mic_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.mic_mute_btn = QPushButton("Mute mic")
        self.mic_mute_btn.clicked.connect(self.toggle_mic_mute)
        mic_row = QHBoxLayout()
        mic_row.setSpacing(10)
        mic_row.addWidget(QLabel("Quiet"))
        mic_row.addWidget(self.mic_slider, 1)
        mic_row.addWidget(QLabel("Loud"))
        mic_row.addWidget(self.mic_value)
        mic_row.addWidget(self.mic_mute_btn)
        mic_holder = QWidget()
        mic_holder.setLayout(mic_row)
        microphone.add(mic_holder)
        self.add(microphone)

        # Devices --------------------------------------------------------
        self.add_section("Devices")
        devices = Card("Sinks and sources")
        self.device_table = DataTable(
            ["Type", "ID", "Name", "State", "Default"],
            stretch_column=2,
            min_height=120,
        )
        self.device_table.set_mono_columns(1, right=True)
        self.device_table.itemDoubleClicked.connect(lambda _item, _col: self.set_default_device())
        devices.add(self.device_table)
        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        refresh_devices = QPushButton("Refresh devices")
        refresh_devices.setObjectName("Ghost")
        refresh_devices.clicked.connect(self.refresh_devices)
        make_default = QPushButton("Set as default")
        make_default.clicked.connect(self.set_default_device)
        device_row.addWidget(refresh_devices)
        device_row.addWidget(make_default)
        device_row.addStretch()
        devices.add_layout(device_row)
        self.add(devices)

        # Media ----------------------------------------------------------
        self.add_section("Media")
        media = Card("playerctl")
        self.now_playing = QLabel("Nothing playing")
        self.now_playing.setObjectName("Accent")
        self.now_playing.setWordWrap(True)
        media.add(self.now_playing)
        self.playback_state = QLabel("")
        self.playback_state.setObjectName("Hint")
        media.add(self.playback_state)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        for label, action in (
            ("Previous", "previous"),
            ("Play / pause", "play-pause"),
            ("Next", "next"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, a=action: self.media_action(a))
            controls.addWidget(button)
        controls.addStretch()
        media.add_layout(controls)
        self.add(media)
        self.add_stretch()

        self._np_timer = QTimer(self)
        self._np_timer.setInterval(3500)
        self._np_timer.timeout.connect(self.refresh_now_playing)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()
        self._np_timer.start()

    def on_hide(self) -> None:
        self._np_timer.stop()

    def refresh(self) -> None:
        self.call(lambda: (audio.get_volume(), audio.get_volume(source=True)), self._apply_volumes)
        self.refresh_devices()
        self.refresh_now_playing()

    def _apply_volumes(self, values) -> None:
        output, microphone = values
        if output is None:
            self.volume_slider.setEnabled(False)
            self.output_hint.setText("No audio server detected (wpctl/pactl not available).")
        else:
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(min(100, output.percent))
            self.volume_slider.blockSignals(False)
            self.volume_slider.setEnabled(True)
            self.volume_value.setText(f"{output.percent}%")
            self.mute_btn.setText("Unmute" if output.muted else "Mute")
            self.output_hint.setText("Muted" if output.muted else "")
        if microphone is None:
            self.mic_slider.setEnabled(False)
        else:
            self.mic_slider.blockSignals(True)
            self.mic_slider.setValue(min(100, microphone.percent))
            self.mic_slider.blockSignals(False)
            self.mic_slider.setEnabled(True)
            self.mic_value.setText(f"{microphone.percent}%")
            self.mic_mute_btn.setText("Unmute mic" if microphone.muted else "Mute mic")

    def _volume_changed(self, value: int) -> None:
        self.volume_value.setText(f"{value}%")
        self._volume_timer.start()

    def _apply_volume(self) -> None:
        value = self.volume_slider.value()

        def done(result) -> None:
            if not result.ok:
                self.notify(result.summary(), "error")

        self.call(lambda: audio.set_volume(value), done)

    def _mic_changed(self, value: int) -> None:
        self.mic_value.setText(f"{value}%")
        self._mic_timer.start()

    def _apply_mic(self) -> None:
        value = self.mic_slider.value()

        def done(result) -> None:
            if not result.ok:
                self.notify(result.summary(), "error")

        self.call(lambda: audio.set_volume(value, source=True), done)

    def toggle_mute(self) -> None:
        self.call(
            lambda: audio.toggle_mute(),
            lambda result: self._after_mute(result, source=False),
        )

    def toggle_mic_mute(self) -> None:
        self.call(
            lambda: audio.toggle_mute(source=True),
            lambda result: self._after_mute(result, source=True),
        )

    def _after_mute(self, result, *, source: bool) -> None:
        if not result.ok:
            self.notify(result.summary(), "error")
        self.call(
            lambda: (audio.get_volume(), audio.get_volume(source=True)),
            self._apply_volumes,
        )

    # ------------------------------------------------------------------
    def refresh_devices(self) -> None:
        self.call(audio.list_devices, self._apply_devices)

    def _apply_devices(self, devices: dict) -> None:
        self.device_table.clear_rows()
        for kind, entries in (
            ("Sink", devices.get("sinks", [])),
            ("Source", devices.get("sources", [])),
        ):
            for device in entries:
                item = QTreeWidgetItem(
                    [
                        kind,
                        device.id,
                        device.name,
                        device.state,
                        "Yes" if device.default else "",
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, (kind, device.name))
                self.device_table.addTopLevelItem(item)
        if self.device_table.topLevelItemCount() == 0:
            self.device_table.addTopLevelItem(
                QTreeWidgetItem(["—", "", "No devices reported", "", ""])
            )
        self.device_table.fit_rows(max_rows=8)

    def set_default_device(self) -> None:
        item = self.device_table.currentItem()
        if item is None:
            self.notify("Select a device first.", "info")
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name = data

        def done(result) -> None:
            if result.ok:
                self.notify(f"Default {kind.lower()} set to {name}.", "success")
            else:
                self.notify(result.summary(), "error")
            self.refresh_devices()

        self.call(lambda: audio.set_default(name, source=(kind == "Source")), done)

    # ------------------------------------------------------------------
    def refresh_now_playing(self) -> None:
        if self._np_busy:
            return
        self._np_busy = True

        def done(track) -> None:
            self._np_busy = False
            if track is None:
                self.now_playing.setText("Nothing playing")
                self.playback_state.setText("playerctl is not available or no player is active.")
                return
            self.now_playing.setText(f"Playing · {track.text}")
            self.playback_state.setText(track.status.capitalize() if track.status else "")

        def failed(_message: str, _trace: str) -> None:
            self._np_busy = False

        self.runner.submit(audio.now_playing, on_done=done, on_error=failed)

    def media_action(self, action: str) -> None:
        def done(result) -> None:
            if not result.ok:
                self.notify(result.summary(), "error")
            self.refresh_now_playing()

        self.call(lambda: audio.player_action(action), done)
