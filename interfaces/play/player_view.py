"""Minimal MIDI song player/viewer for Play mode."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from interfaces.audio.midi_player import FluidSynthMidiPlayer
from interfaces.audio.midi_rendering import FilteredMidiRenderRequest, FilteredMidiRenderer
from interfaces.play.midi_targets import discover_midi_songs, load_midi_song
from interfaces.play.model import PlaySong
from interfaces.play.playback import PlaybackController, PlaybackState
from interfaces.play.view import PianoRollTimeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PlayerView(QWidget):
    """Show bundled MIDI songs and play them with one authoritative transport."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._songs: list[PlaySong] = []
        self._song: PlaySong | None = None
        self._transport = PlaybackController()
        self._player = FluidSynthMidiPlayer()
        self._renderer = FilteredMidiRenderer()
        self._temporary_midi: Path | None = None

        self.back_button = QPushButton("Back")
        self.song_combo = QComboBox()
        self.restart_button = QPushButton("Restart")
        self.play_pause_button = QPushButton("Play")
        self.time_label = QLabel("0:00 / 0:00")
        self.status_label = QLabel("Loading bundled MIDI songs…")
        self.timeline = PianoRollTimeline()
        self.timeline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.timeline.setMinimumHeight(420)

        top = QHBoxLayout()
        top.addWidget(self.back_button)
        top.addWidget(QLabel("Play"))
        top.addStretch(1)
        top.addWidget(QLabel("Song"))
        top.addWidget(self.song_combo, 2)
        transport = QHBoxLayout()
        transport.addWidget(self.restart_button)
        transport.addWidget(self.play_pause_button)
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addLayout(top)
        layout.addWidget(self.timeline, 1)
        layout.addLayout(transport)
        layout.addWidget(self.status_label)

        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self.back_button.clicked.connect(self._go_back)
        self.song_combo.currentIndexChanged.connect(self._select_song)
        self.play_pause_button.clicked.connect(self._toggle_playback)
        self.restart_button.clicked.connect(self._restart)
        self._load_songs()

    def activate(self) -> None:
        """Activate the viewer; no input device is owned by Play."""

    def deactivate(self) -> None:
        """Stop Play-owned MIDI playback when this screen is left."""

        self._stop_playback()

    def closeEvent(self, event: object) -> None:
        """Release the external MIDI process when the window closes."""

        self.deactivate()
        super().closeEvent(event)

    def _load_songs(self) -> None:
        errors: list[str] = []
        self.song_combo.blockSignals(True)
        for midi_path in discover_midi_songs(PROJECT_ROOT):
            try:
                song = load_midi_song(midi_path, include_drums=True)
            except Exception as exc:
                errors.append(f"{midi_path.name}: {exc}")
                continue
            self._songs.append(song)
            self.song_combo.addItem(song.title, song)
        self.song_combo.blockSignals(False)
        if self._songs:
            self.song_combo.setCurrentIndex(0)
            self._select_song(0)
        else:
            self.status_label.setText("No bundled MIDI could be loaded. " + (errors[0] if errors else ""))
            self.play_pause_button.setEnabled(False)

    def _select_song(self, index: int) -> None:
        self._stop_playback()
        song = self.song_combo.itemData(index)
        self._song = song if isinstance(song, PlaySong) else None
        if self._song is None:
            self.timeline.set_song(None)
            self._render(self._transport.load(0.0))
            return
        self.timeline.set_song(self._song)
        self.timeline.set_playhead(self._song.start_time)
        self._render(self._transport.load(self._song.end_time - self._song.start_time))
        self.status_label.setText(f"{self._song.title}: {len(self._song.tracks)} MIDI tracks")

    def _toggle_playback(self) -> None:
        if self._song is None or self._song.path is None:
            return
        now = time.monotonic()
        state = self._transport.snapshot()
        if state.is_playing:
            self._stop_playback(now)
            return
        try:
            self._start_audio_at(state.position)
        except (OSError, RuntimeError) as exc:
            self.status_label.setText(f"MIDI playback unavailable: {exc}")
        else:
            state = self._transport.play(time.monotonic())
            self.status_label.setText("Playing")
            self._timer.start()
        self._render(self._transport.snapshot())

    def _start_audio_at(self, position: float) -> None:
        assert self._song is not None and self._song.path is not None
        source_duration = max(0.0, self._song.end_time - self._song.start_time)
        start_time = self._song.start_time + min(max(0.0, position), source_duration)
        output = Path(tempfile.gettempdir()) / "guitar-hero-playback.mid"
        self._temporary_midi = self._renderer.render(FilteredMidiRenderRequest(
            source_path=self._song.path,
            output_path=output,
            track_indexes=frozenset(track.index for track in self._song.tracks),
            start_time=start_time,
            end_time=self._song.end_time,
        ))
        self._player.play(self._temporary_midi)

    def _restart(self) -> None:
        self._stop_playback()
        self._render(self._transport.restart())
        self.status_label.setText("Ready")

    def _stop_playback(self, now: float | None = None) -> None:
        if now is not None:
            self._transport.pause(now)
        elif self._transport.snapshot().is_playing:
            self._transport.pause(time.monotonic())
        self._player.stop()
        self._timer.stop()
        self._render(self._transport.snapshot())

    def _tick(self) -> None:
        state = self._transport.update(time.monotonic())
        if not state.is_playing:
            self._player.stop()
            self._timer.stop()
            self.status_label.setText("Finished")
        self._render(state)

    def _render(self, state: PlaybackState) -> None:
        source_start = self._song.start_time if self._song is not None else 0.0
        self.timeline.set_playhead(source_start + state.position)
        self.play_pause_button.setText("Pause" if state.is_playing else "Play")
        self.time_label.setText(f"{_format_time(state.position)} / {_format_time(state.duration)}")

    def _go_back(self) -> None:
        self.deactivate()
        self.back_requested.emit()


def _format_time(seconds: float) -> str:
    """Format a source-MIDI duration for the compact transport readout."""

    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"
