"""Qt adapter for Play mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from interfaces.debug_dump import dump
from interfaces.audio.pitch import (
    AudioDevice,
    LivePitchInput,
    PitchFrame,
    PluckDetector,
    SpectrumPeak,
    list_input_devices,
    note_to_frequency,
)
from interfaces.play.controller import PlayController
from interfaces.play.midi_targets import demo_song, discover_midi_songs, load_midi_song, midi_note_name
from interfaces.play.model import (
    Feedback,
    PlaySection,
    PlaySong,
    PlayTarget,
    MidiTrackOption,
    TimeRegion,
)
from interfaces.play.transposition import (
    TRANSPOSE_MAX_SEMITONES,
    TRANSPOSE_MIN_SEMITONES,
    apply_transpose,
    clamp_transpose,
    note_range_for_targets,
    transpose_section,
    validate_guitar_range,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDLE_HIT_RADIUS = 10
PLAY_LOOKAHEAD_SECONDS = 15.0


@dataclass
class TrackUiState:
    """Mutable Qt-side controls for one loaded MIDI track.

    Visibility is a display-only control. Keeping it outside
    ``PlayController`` prevents chart context from becoming target-generation
    policy.

    @author Codex - added Play piano-roll track UI state.
    @author Codex - removed Play Run Mode playback state.
    """

    visible: bool = True


class MidiOverviewBar(QWidget):
    """Full-song MIDI overview with a locked lookahead window.

    The overview is a Qt navigation adapter, not scoring policy. It owns the
    display window shown by ``PianoRollTimeline`` while Play target selection
    and scoring timing remain in ``PlayController``.

    @author Codex - added Play MIDI overview viewport control.
    @author Codex - locked Play overview to the next 15 seconds.
    """

    playhead_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(72)
        self.setMaximumHeight(82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._song: PlaySong | None = None
        self._display_window = TimeRegion(0.0, 0.0)
        self._playhead_time = 0.0
        self._dragging_playhead = False

    def set_song(self, song: PlaySong | None, window: TimeRegion | None = None) -> None:
        """Load the full MIDI bounds represented by the overview bar.

        @author Codex - added Play MIDI overview viewport control.
        """

        self._song = song
        if song is None:
            self._display_window = TimeRegion(0.0, 0.0)
            self._playhead_time = 0.0
        else:
            self._display_window = self._clamp_window(
                window or TimeRegion(song.start_time, song.end_time)
            )
            self._playhead_time = song.start_time
        self.update()

    def set_display_window(self, start_time: float, end_time: float) -> None:
        """Render an externally selected piano-roll display window.

        @author Codex - added Play MIDI overview viewport control.
        """

        if self._song is None:
            self._display_window = TimeRegion(0.0, 0.0)
        else:
            self._display_window = self._clamp_window(TimeRegion(start_time, end_time))
        self.update()

    def set_playhead(self, playhead_time: float) -> None:
        """Render the current Play song position in the overview.

        @author Codex - added Play overview playhead.
        """

        if self._song is None:
            self._playhead_time = 0.0
        else:
            self._playhead_time = max(self._song.start_time, min(playhead_time, self._song.end_time))
        self.update()

    def paintEvent(self, event: object) -> None:
        """Paint the full MIDI duration and the visible piano-roll window.

        @author Codex - added Play MIDI overview viewport control.
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1118"))

        bar_rect = self._bar_rect()
        painter.setPen(QPen(QColor("#26364a"), 1))
        painter.setBrush(QColor("#111824"))
        painter.drawRoundedRect(bar_rect, 6, 6)

        if self._song is None or not self._song.tracks:
            painter.setPen(QColor("#b8c7dc"))
            painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, "Load a MIDI song to view the next 15 seconds.")
            painter.end()
            return

        self._paint_note_overview(painter, bar_rect)
        start_x = self._time_to_x(self._display_window.start_time)
        end_x = self._time_to_x(self._display_window.end_time)
        selected = QRectF(start_x, bar_rect.top(), max(1.0, end_x - start_x), bar_rect.height())
        painter.fillRect(selected, QColor(33, 212, 253, 42))
        painter.setPen(QPen(QColor("#21d4fd"), 2))
        painter.drawRoundedRect(selected, 4, 4)
        playhead_x = self._time_to_x(self._playhead_time)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(int(playhead_x), int(bar_rect.top() - 8), int(playhead_x), int(bar_rect.bottom() + 8))
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#05070a"), 1))
        painter.drawRoundedRect(QRectF(playhead_x - 5, bar_rect.top() - 12, 10, 12), 3, 3)

        painter.setPen(QColor("#91a4bd"))
        painter.drawText(QPoint(int(bar_rect.left()), int(bar_rect.top() - 5)), "Next 15 seconds")
        painter.drawText(QPoint(int(bar_rect.left()), int(bar_rect.bottom() + 16)), f"{self._song.start_time:.1f}s")
        painter.drawText(QPoint(int(bar_rect.right() - 44), int(bar_rect.bottom() + 16)), f"{self._song.end_time:.1f}s")
        painter.end()

    def mousePressEvent(self, event: object) -> None:
        """Choose the Play start position from the overview.

        @author Codex - added draggable Play overview start position.
        """

        if self._song is None:
            return
        self._dragging_playhead = True
        self._move_playhead_from_event(event)

    def mouseMoveEvent(self, event: object) -> None:
        """Drag the Play start position through the overview.

        @author Codex - added draggable Play overview start position.
        """

        if not self._dragging_playhead:
            return
        self._move_playhead_from_event(event)

    def mouseReleaseEvent(self, event: object) -> None:
        """Finish dragging the Play overview playhead.

        @author Codex - added draggable Play overview start position.
        """

        if self._dragging_playhead:
            self._move_playhead_from_event(event)
        self._dragging_playhead = False

    def _bar_rect(self) -> QRectF:
        """Return the drawable overview rectangle.

        @author Codex - added Play MIDI overview viewport control.
        """

        return QRectF(self.rect()).adjusted(12, 22, -12, -22)

    def _time_to_x(self, seconds: float) -> float:
        """Map full-song seconds to an overview x coordinate.

        @author Codex - added Play MIDI overview viewport control.
        """

        if self._song is None:
            return self._bar_rect().left()
        rect = self._bar_rect()
        duration = max(self._song.end_time - self._song.start_time, 0.001)
        ratio = (seconds - self._song.start_time) / duration
        return rect.left() + max(0.0, min(1.0, ratio)) * rect.width()

    def _x_to_time(self, x: float) -> float:
        """Map an overview x coordinate back to full-song seconds.

        @author Codex - added draggable Play overview start position.
        """

        if self._song is None:
            return 0.0
        rect = self._bar_rect()
        ratio = (x - rect.left()) / max(rect.width(), 1.0)
        ratio = max(0.0, min(1.0, ratio))
        return self._song.start_time + ratio * max(self._song.end_time - self._song.start_time, 0.0)

    def _move_playhead_from_event(self, event: object) -> None:
        """Set and emit the overview playhead from a Qt mouse event.

        @author Codex - added draggable Play overview start position.
        """

        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self.set_playhead(self._x_to_time(position.x()))
        self.playhead_changed.emit(self._playhead_time)

    def _paint_note_overview(self, painter: QPainter, rect: QRectF) -> None:
        """Paint compact note density lanes for the full MIDI.

        @author Codex - added Play MIDI overview viewport control.
        """

        assert self._song is not None
        lane_count = max(1, len(self._song.tracks))
        lane_height = rect.height() / lane_count
        for lane_index, track in enumerate(self._song.tracks):
            y = rect.top() + lane_index * lane_height
            color = QColor(track.color)
            color.setAlpha(150)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            for note in track.notes:
                x1 = self._time_to_x(note.start_time)
                x2 = max(x1 + 1, self._time_to_x(note.end_time))
                painter.drawRect(QRectF(x1, y + 2, x2 - x1, max(2.0, lane_height - 4)))

    def _clamp_window(self, window: TimeRegion) -> TimeRegion:
        """Clamp the displayed window to full-song bounds.

        @author Codex - added Play MIDI overview viewport control.
        """

        if self._song is None:
            return TimeRegion(0.0, 0.0)
        duration = max(self._song.end_time - self._song.start_time, 0.0)
        minimum_duration = min(max(duration * 0.02, 0.05), duration) if duration else 0.0
        return window.clamp(self._song.start_time, self._song.end_time, minimum_duration=minimum_duration)


class PianoRollTimeline(QWidget):
    """Piano-roll timeline for visible Play chart context.

    This widget paints MIDI note spans by pitch and time. It does not choose
    the target track or advance scoring; those decisions stay in the view
    composition and ``PlayController`` respectively.

    @author Codex - replaced Play target lane with piano-roll timeline.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._song: PlaySong | None = None
        self._visible_track_indexes: frozenset[int] = frozenset()
        self._target_track_index: int | None = None
        self._display_window = TimeRegion(0.0, 0.0)
        self._current_target: PlayTarget | None = None
        self._passed_indexes: frozenset[int] = frozenset()
        self._missed_indexes: frozenset[int] = frozenset()
        self._transpose_semitones = 0

    def set_song(self, song: PlaySong | None) -> None:
        """Render the loaded song context on the piano roll.

        @author Codex - added Play piano-roll song rendering.
        @author Codex - initialized Play piano-roll display window.
        """

        self._song = song
        self._visible_track_indexes = frozenset(track.index for track in song.tracks) if song else frozenset()
        self._target_track_index = None
        self._display_window = (
            TimeRegion(song.start_time, song.end_time)
            if song is not None
            else TimeRegion(0.0, 0.0)
        )
        self._current_target = None
        self._passed_indexes = frozenset()
        self._missed_indexes = frozenset()
        self.update()

    def set_display_window(self, start_time: float, end_time: float) -> None:
        """Limit the piano roll to the overview-selected visible MIDI range.

        This is a viewport concern only. It deliberately does not change the
        controller's scoring bounds or selected Play targets.

        @author Codex - added Play piano-roll display window.
        """

        if self._song is None:
            self._display_window = TimeRegion(0.0, 0.0)
        else:
            duration = max(self._song.end_time - self._song.start_time, 0.0)
            minimum_duration = min(max(duration * 0.02, 0.05), duration) if duration else 0.0
            self._display_window = TimeRegion(start_time, end_time).clamp(
                self._song.start_time,
                self._song.end_time,
                minimum_duration=minimum_duration,
            )
        self.update()

    def set_transpose(self, semitones: int) -> None:
        """Shift the displayed target track without changing raw MIDI notes.

        The piano roll is a Play chart view. The selected target track uses
        the same transposition as matching, while context tracks remain raw
        imported MIDI material.

        @author Codex - added Play piano-roll transposition rendering.
        """

        self._transpose_semitones = clamp_transpose(semitones)
        self.update()

    def set_visible_tracks(self, track_indexes: frozenset[int]) -> None:
        """Apply visibility state for chart context tracks.

        @author Codex - added Play piano-roll visibility control.
        @author Codex - removed Play Run Mode playback controls.
        """

        self._visible_track_indexes = track_indexes
        self.update()

    def set_target_track(self, track_index: int | None) -> None:
        """Mark which track generates Play targets.

        @author Codex - added Play piano-roll target track highlighting.
        """

        self._target_track_index = track_index
        self.update()

    def set_state(
        self,
        *,
        current_target: PlayTarget | None,
        passed_indexes: frozenset[int],
        missed_indexes: frozenset[int],
    ) -> None:
        """Update dynamic timeline state from the controller snapshot.

        @author Codex - updated Play timeline state for piano roll.
        @author Codex - removed playhead state from the piano-roll timeline.
        """

        self._current_target = current_target
        self._passed_indexes = passed_indexes
        self._missed_indexes = missed_indexes
        self.update()

    def paintEvent(self, event: object) -> None:
        """Paint pitch lanes and visible MIDI notes.

        @author Codex - replaced Play timeline rendering with piano roll.
        @author Codex - moved Play playhead rendering into a dedicated bar.
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1118"))

        roll_rect = self._roll_rect()
        painter.fillRect(roll_rect, QColor("#111824"))
        painter.setPen(QPen(QColor("#26364a"), 1))
        painter.drawRoundedRect(roll_rect, 6, 6)

        if self._song is None or not self._song.tracks:
            painter.setPen(QColor("#b8c7dc"))
            painter.drawText(roll_rect, Qt.AlignmentFlag.AlignCenter, "Load a MIDI song to inspect its tracks.")
            painter.end()
            return

        self._paint_pitch_grid(painter, roll_rect)
        self._paint_time_grid(painter, roll_rect)
        self._paint_notes(painter, roll_rect)
        painter.end()

    def _roll_rect(self) -> QRectF:
        """Return the drawable piano-roll rectangle.

        @author Codex - added Play piano-roll geometry.
        """

        return QRectF(self.rect()).adjusted(58, 28, -18, -38)

    def _timeline_bounds(self) -> tuple[float, float]:
        """Return visible timeline bounds.

        @author Codex - added Play piano-roll geometry.
        @author Codex - made Play piano-roll bounds follow the overview viewport.
        """

        if self._song is None:
            return (0.0, 0.0)
        return (self._display_window.start_time, self._display_window.end_time)

    def _pitch_bounds(self) -> tuple[int, int]:
        """Return visible MIDI pitch bounds with a small vertical pad.

        @author Codex - added Play piano-roll geometry.
        @author Codex - limited Play piano-roll pitch bounds to the displayed window.
        """

        if self._song is None:
            return (40, 64)
        visible_start, visible_end = self._timeline_bounds()
        notes: list[int] = []
        for track in self._song.tracks:
            if track.notes:
                notes.extend(
                    self._display_note_for_track(track.index, note.midi_note)
                    for note in track.notes
                    if note.end_time >= visible_start and note.start_time <= visible_end
                )
                continue
            for target in track.section.targets:
                if not visible_start <= target.start_time <= visible_end:
                    continue
                notes.extend(
                    self._display_note_for_track(track.index, midi_note)
                    for midi_note in target.original_midi_notes
                )
        if not notes:
            low, high = self._song.pitch_range
        else:
            low, high = min(notes), max(notes)
        return (max(0, low - 1), min(127, high + 1))

    def _time_to_x(self, seconds: float) -> float:
        """Map song seconds to an x coordinate.

        @author Codex - added Play piano-roll geometry.
        """

        rect = self._roll_rect()
        start_time, end_time = self._timeline_bounds()
        duration = max(end_time - start_time, 0.001)
        ratio = (seconds - start_time) / duration
        return rect.left() + max(0.0, min(1.0, ratio)) * rect.width()

    def _note_to_y(self, midi_note: int, rect: QRectF) -> float:
        """Map a MIDI note to the top y coordinate of its pitch lane.

        @author Codex - added Play piano-roll geometry.
        """

        min_note, max_note = self._pitch_bounds()
        lane_count = max(1, max_note - min_note + 1)
        lane_height = rect.height() / lane_count
        return rect.top() + (max_note - midi_note) * lane_height

    def _paint_pitch_grid(self, painter: QPainter, rect: QRectF) -> None:
        """Paint horizontal pitch lanes and note labels.

        @author Codex - added Play piano-roll pitch axis.
        """

        min_note, max_note = self._pitch_bounds()
        lane_count = max(1, max_note - min_note + 1)
        lane_height = rect.height() / lane_count
        for note in range(min_note, max_note + 1):
            y = self._note_to_y(note, rect)
            is_octave_c = note % 12 == 0
            painter.setPen(QPen(QColor("#26364a" if is_octave_c else "#1d2a3a"), 1))
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            if is_octave_c or lane_height >= 13:
                painter.setPen(QColor("#7f8da3"))
                painter.drawText(QPoint(8, int(y + max(10, lane_height * 0.75))), midi_note_name(note))

    def _paint_time_grid(self, painter: QPainter, rect: QRectF) -> None:
        """Paint measure marks when available, otherwise coarse seconds.

        @author Codex - added Play piano-roll time axis.
        @author Codex - limited Play piano-roll time grid to the displayed window.
        """

        assert self._song is not None
        start_time, end_time = self._timeline_bounds()
        marks = [mark for mark in self._song.measure_marks if start_time <= mark.start_time <= end_time]
        if marks:
            for mark in marks:
                x = self._time_to_x(mark.start_time)
                painter.setPen(QPen(QColor("#334761"), 1))
                painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
                painter.setPen(QColor("#91a4bd"))
                painter.drawText(QPoint(int(x + 4), int(rect.top() - 8)), mark.label)
            return

        duration = max(end_time - start_time, 0.001)
        tick_count = max(4, min(12, int(rect.width() // 90)))
        painter.setPen(QPen(QColor("#25344a"), 1))
        for index in range(tick_count + 1):
            ratio = index / tick_count
            x = rect.left() + ratio * rect.width()
            seconds = start_time + ratio * duration
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            painter.setPen(QColor("#7f8da3"))
            painter.drawText(QPoint(int(x + 4), int(rect.bottom() + 18)), f"{seconds:.1f}s")
            painter.setPen(QPen(QColor("#25344a"), 1))

    def _paint_notes(self, painter: QPainter, rect: QRectF) -> None:
        """Paint visible MIDI note spans as colored piano-roll rectangles.

        @author Codex - added Play piano-roll note rendering.
        @author Codex - limited Play piano-roll note rendering to the displayed window.
        """

        assert self._song is not None
        visible_start, visible_end = self._timeline_bounds()
        min_note, max_note = self._pitch_bounds()
        lane_height = rect.height() / max(1, max_note - min_note + 1)
        for track in self._song.tracks:
            if track.index not in self._visible_track_indexes:
                continue
            base_color = QColor(track.color)
            is_target_track = track.index == self._target_track_index
            for note in track.notes:
                if note.end_time < visible_start or note.start_time > visible_end:
                    continue
                x1 = self._time_to_x(note.start_time)
                x2 = max(x1 + 2, self._time_to_x(note.end_time))
                if x2 < rect.left() or x1 > rect.right():
                    continue
                y = self._note_to_y(self._display_note_for_track(track.index, note.midi_note), rect)
                height = max(4.0, lane_height - 1.0)
                block = QRectF(
                    max(rect.left(), x1),
                    y + 1,
                    min(x2, rect.right()) - max(rect.left(), x1),
                    height,
                )
                color = QColor(base_color)
                color.setAlpha(235 if is_target_track else 150)
                painter.setBrush(color)
                painter.setPen(QPen(QColor("#05070a"), 1))
                painter.drawRoundedRect(block, 2, 2)

    def _display_note_for_track(self, track_index: int, midi_note: int) -> int:
        """Return the pitch shown for a piano-roll note.

        @author Codex - added Play piano-roll transposition rendering.
        """

        if track_index == self._target_track_index:
            return int(midi_note) + self._transpose_semitones
        return int(midi_note)

class PlayView(QWidget):
    """MIDI-driven song-scoring screen.

    Play is a scoring surface, so the view shows a piano-roll timeline and track
    controls. MIDI parsing, target matching, and live input
    stay behind explicit boundaries.

    @author Codex - created first Play mode screen.
    @author Codex - replaced Play highway-like timeline with piano roll.
    """

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._controller = PlayController()
        self._songs: list[PlaySong] = []
        self._current_song: PlaySong | None = None
        self._target_track: MidiTrackOption | None = None
        self._track_states: dict[int, TrackUiState] = {}
        self._track_rows: dict[int, QFrame] = {}
        self._track_detail_labels: dict[int, QLabel] = {}
        self._target_radios: dict[int, QRadioButton] = {}
        self._transpose_semitones = 0
        self._input = LivePitchInput()
        self._pluck_detector = PluckDetector()
        self._devices: list[AudioDevice] = []
        self._latest_detected_notes: tuple[int, ...] = ()
        self._running = False
        self._frame_count = 0
        self._last_readout_at = 0.0
        self._last_frame_dump_at = 0.0

        self.song_combo = QComboBox()
        self.device_combo = QComboBox()
        self.device_combo.setObjectName("inputDeviceCombo")
        self.refresh_button = QPushButton("Refresh Devices")
        self.refresh_button.setObjectName("refreshDevicesButton")
        self.start_button = QPushButton()
        self.start_button.setObjectName("inputToggleButton")
        self.start_button.setAccessibleName("Start input")
        self.start_button.setToolTip("Start input")
        self.play_pause_button = QPushButton(">")
        self.play_pause_button.setObjectName("playPauseButton")
        self.play_pause_button.setAccessibleName("Play")
        self.play_pause_button.setToolTip("Play from the current song position")
        self.play_pause_button.setFixedSize(44, 38)
        self.restart_button = QPushButton("<<")
        self.restart_button.setObjectName("restartButton")
        self.restart_button.setAccessibleName("Restart")
        self.restart_button.setToolTip("Restart from the beginning")
        self.restart_button.setFixedSize(44, 38)
        self.speed_combo = QComboBox()
        self.speed_combo.setObjectName("playSpeedCombo")
        self.speed_combo.setAccessibleName("Play speed")
        self.speed_combo.setToolTip("Set Play song speed")
        for label, multiplier in (
            ("0.25x", 0.25),
            ("0.33x", 1.0 / 3.0),
            ("0.5x", 0.5),
            ("0.75x", 0.75),
            ("1x", 1.0),
            ("1.25x", 1.25),
            ("1.5x", 1.5),
        ):
            self.speed_combo.addItem(label, multiplier)
        self.speed_combo.setCurrentIndex(4)
        self.sample_rate_label = QLabel("Sample rate: --")
        self.transpose_spin = QSpinBox()
        self.transpose_spin.setRange(TRANSPOSE_MIN_SEMITONES, TRANSPOSE_MAX_SEMITONES)
        self.transpose_spin.setValue(0)
        self.transpose_spin.setSuffix(" st")
        self.transpose_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.transpose_down_button = QPushButton("-")
        self.transpose_down_button.setObjectName("transposeStepDown")
        self.transpose_down_button.setAccessibleName("Transpose down")
        self.transpose_down_button.setToolTip("Transpose down one semitone")
        self.transpose_down_button.setFixedSize(38, 36)
        self.transpose_up_button = QPushButton("+")
        self.transpose_up_button.setObjectName("transposeStepUp")
        self.transpose_up_button.setAccessibleName("Transpose up")
        self.transpose_up_button.setToolTip("Transpose up one semitone")
        self.transpose_up_button.setFixedSize(38, 36)
        self.transpose_value_label = QLabel("+0")
        self.transpose_value_label.setObjectName("transposeValue")
        self.transpose_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.transpose_value_label.setFixedSize(62, 36)
        self.transpose_preview_label = QLabel("Transpose: +0 semitones")
        self.transpose_preview_label.setObjectName("transposePreview")
        self.lowest_note_label = QLabel("Lowest note: --")
        self.lowest_note_label.setFixedWidth(112)
        self.highest_note_label = QLabel("Highest note: --")
        self.highest_note_label.setFixedWidth(120)
        self.range_warning_label = QLabel("")
        self.transpose_panel = QFrame()
        self.transpose_panel.setObjectName("transposePanel")
        self.back_button = QPushButton("Back")
        self.status_label = QLabel("Choose a MIDI song and target track.")
        self.timeline_overview = MidiOverviewBar()
        self.timeline_overview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.timeline = PianoRollTimeline()
        self.timeline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.target_view_button = QPushButton("Target")
        self.target_view_button.setCheckable(True)
        self.target_view_button.setChecked(True)
        self.tracks_view_button = QPushButton("Tracks")
        self.tracks_view_button.setCheckable(True)
        self.track_panel = QFrame()
        self.track_panel.setObjectName("trackPanel")
        self.track_list = QVBoxLayout(self.track_panel)
        self.track_list.setContentsMargins(10, 10, 10, 10)
        self.track_list.setSpacing(8)
        self.target_group = QButtonGroup(self)
        self.target_group.setExclusive(True)
        self.current_target_label = QLabel("--")
        self.expected_label = QLabel("Choose a target track to generate Play targets.")
        self.detected_label = QLabel("Detected: --")
        self.feedback_label = QLabel(Feedback.IDLE.value)
        self.progress_label = QLabel("0 / 0 targets")
        self.hit_label = QLabel("Hit:")
        self.hit_count_label = QLabel("0")
        self.miss_label = QLabel("Miss:")
        self.miss_count_label = QLabel("0")
        self.hit_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.miss_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_input_button()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._update_frame)

        self._build_layout()
        self._apply_style()
        self._connect_signals()
        self.refresh_devices()
        self._load_songs()
        self._render_state()
        dump("play", "ready")

    def activate(self) -> None:
        """Start Play's live detector when the screen becomes active.

        @author Codex - created Play screen activation lifecycle.
        @author Codex - aligned Play input lifecycle with Sandbox.
        """

        if not self._running:
            dump("play", "activate")
            self.start_input()

    def deactivate(self) -> None:
        """Stop resources owned by Play when leaving the screen.

        @author Codex - created Play screen activation lifecycle.
        @author Codex - removed Play Run Mode playback lifecycle.
        @author Codex - stopped Play playback when leaving the screen.
        """

        self._controller.pause(time.monotonic())
        self.stop_input()
        self._sync_timer()
        dump("play", "deactivate")

    def closeEvent(self, event: object) -> None:
        """Release Play input resources when the widget closes.

        @author Codex - created Play screen activation lifecycle.
        """

        self.deactivate()
        super().closeEvent(event)

    def _build_layout(self) -> None:
        """Build the Play screen layout.

        @author Codex - created first Play mode screen.
        @author Codex - replaced Play layout with piano roll and track panel.
        @author Codex - moved Play readouts into the side rail to prioritize the piano roll.
        @author Codex - added Play MIDI overview above the piano roll.
        @author Codex - added a dedicated Play playhead bar.
        @author Codex - removed Play Run Mode controls.
        @author Codex - added side-rail view switcher for target status versus tracks.
        @author Codex - compacted song and transpose controls in the Play toolbar.
        @author Codex - grouped Play transpose controls and range readout.
        @author Codex - replaced visible transpose spinbox with segmented stepper.
        @author Codex - arranged Play transpose details as explicit note readouts.
        @author Codex - compacted Play transpose details into one toolbar line.
        @author Codex - matched Play input controls layout to Sandbox.
        """

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Play")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.back_button)
        root.addLayout(top)

        controls = QFrame()
        controls.setObjectName("controlsStack")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        input_panel = QFrame()
        input_panel.setObjectName("panel")
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.addWidget(QLabel("Input"))
        input_layout.addWidget(self.device_combo, 1)
        input_layout.addWidget(self.refresh_button)
        input_layout.addWidget(self.start_button)
        input_layout.addWidget(self.sample_rate_label)
        controls_layout.addWidget(input_panel)

        song_panel = QFrame()
        song_panel.setObjectName("panel")
        song_layout = QHBoxLayout(song_panel)
        song_layout.setContentsMargins(12, 10, 12, 10)
        song_layout.setSpacing(6)
        song_picker = QWidget()
        song_picker_layout = QHBoxLayout(song_picker)
        song_picker_layout.setContentsMargins(0, 0, 0, 0)
        song_picker_layout.setSpacing(6)
        song_picker_layout.addWidget(QLabel("Song"))
        song_picker_layout.addWidget(self.song_combo, 1)
        song_layout.addWidget(song_picker, 1)
        song_layout.addWidget(self.transpose_panel, 1)
        controls_layout.addWidget(song_panel)
        root.addWidget(controls)

        self.status_label.setObjectName("status")
        root.addWidget(self.status_label)

        transpose_layout = QHBoxLayout(self.transpose_panel)
        transpose_layout.setContentsMargins(10, 8, 10, 8)
        transpose_layout.setSpacing(8)
        transpose_title = QLabel("Transpose")
        transpose_title.setObjectName("transposeTitle")
        transpose_layout.addWidget(transpose_title)
        self.transpose_spin.setVisible(False)
        transpose_layout.addWidget(self.transpose_down_button)
        transpose_layout.addWidget(self.transpose_up_button)
        transpose_layout.addWidget(self.transpose_value_label)
        transpose_layout.addWidget(self.lowest_note_label)
        transpose_layout.addWidget(self.highest_note_label)
        transpose_layout.addStretch(1)

        side = QWidget()
        side.setMinimumWidth(340)
        side.setMaximumWidth(380)
        side.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(8)

        switcher = QHBoxLayout()
        switcher.setSpacing(6)
        switcher.addWidget(self.target_view_button)
        switcher.addWidget(self.tracks_view_button)
        side_layout.addLayout(switcher)

        target_panel = self._info_panel("Current Target")
        target_panel.layout().addWidget(self.current_target_label)
        target_panel.layout().addWidget(self.expected_label)

        feedback_panel = self._info_panel("Feedback")
        feedback_panel.layout().addWidget(self.feedback_label)
        feedback_panel.layout().addWidget(self.detected_label)
        feedback_panel.layout().addWidget(self.progress_label)

        playback_panel = self._info_panel("Playback")
        playback_buttons = QHBoxLayout()
        playback_buttons.setContentsMargins(0, 0, 0, 0)
        playback_buttons.setSpacing(8)
        playback_buttons.addWidget(self.play_pause_button)
        playback_buttons.addWidget(self.restart_button)
        playback_buttons.addWidget(QLabel("Speed"))
        playback_buttons.addWidget(self.speed_combo, 1)
        playback_panel.layout().addLayout(playback_buttons)
        hit_miss_row = QHBoxLayout()
        hit_miss_row.setContentsMargins(0, 0, 0, 0)
        hit_miss_row.setSpacing(8)
        hit_miss_row.addStretch(1)
        hit_miss_row.addWidget(self.hit_label)
        hit_miss_row.addWidget(self.hit_count_label)
        hit_miss_row.addSpacing(18)
        hit_miss_row.addWidget(self.miss_label)
        hit_miss_row.addWidget(self.miss_count_label)
        hit_miss_row.addStretch(1)
        playback_panel.layout().addLayout(hit_miss_row)

        target_status_page = QWidget()
        target_status_layout = QVBoxLayout(target_status_page)
        target_status_layout.setContentsMargins(0, 0, 0, 0)
        target_status_layout.setSpacing(8)
        target_status_layout.addWidget(target_panel)
        target_status_layout.addWidget(feedback_panel)
        target_status_layout.addWidget(playback_panel)
        target_status_layout.addStretch(1)

        tracks_panel = QWidget()
        tracks_layout = QVBoxLayout(tracks_panel)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.setSpacing(8)
        track_title = QLabel("Tracks")
        track_title.setObjectName("sectionTitle")
        tracks_layout.addWidget(track_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.track_panel)
        tracks_layout.addWidget(scroll, 1)

        self.side_stack = QStackedWidget()
        self.side_stack.addWidget(target_status_page)
        self.side_stack.addWidget(tracks_panel)
        side_layout.addWidget(self.side_stack, 1)

        overview_panel = QFrame()
        overview_panel.setObjectName("timelineOverviewPanel")
        overview_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        overview_layout = QVBoxLayout(overview_panel)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.addWidget(self.timeline_overview)

        piano_roll_panel = QFrame()
        piano_roll_panel.setObjectName("pianoRollPanel")
        piano_roll_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        piano_roll_layout = QVBoxLayout(piano_roll_panel)
        piano_roll_layout.setContentsMargins(0, 0, 0, 0)
        piano_roll_layout.addWidget(self.timeline)

        timeline_column = QVBoxLayout()
        timeline_column.setSpacing(10)
        timeline_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        timeline_column.addWidget(overview_panel)
        timeline_column.addWidget(piano_roll_panel, 1)

        middle = QHBoxLayout()
        middle.setSpacing(10)
        middle.addLayout(timeline_column, 1)
        middle.addWidget(side)
        root.addLayout(middle, 10)

        self.current_target_label.setObjectName("targetName")
        self.expected_label.setObjectName("monoText")
        self.expected_label.setWordWrap(True)
        self.transpose_preview_label.setWordWrap(True)
        self.lowest_note_label.setObjectName("rangeText")
        self.lowest_note_label.setProperty("rangeState", "normal")
        self.highest_note_label.setObjectName("rangeText")
        self.highest_note_label.setProperty("rangeState", "normal")
        self.range_warning_label.setObjectName("rangeText")
        self.range_warning_label.setWordWrap(True)
        self.detected_label.setObjectName("monoText")
        self.detected_label.setWordWrap(True)
        self.hit_label.setObjectName("monoText")
        self.miss_label.setObjectName("monoText")
        self.hit_count_label.setObjectName("hitCount")
        self.miss_count_label.setObjectName("missCount")
        self.feedback_label.setObjectName("feedback")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _info_panel(self, title: str) -> QFrame:
        """Create a titled information panel for Play status.

        @author Codex - created first Play mode screen.
        @author Codex - made Play status panels compact inside the side rail.
        """

        panel = QFrame()
        panel.setObjectName("infoPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        return panel

    def _connect_signals(self) -> None:
        """Wire Qt controls to Play controller actions.

        @author Codex - created first Play mode screen.
        @author Codex - connected Play piano-roll track controls.
        @author Codex - connected Play MIDI overview viewport control.
        @author Codex - connected explicit Play transpose step buttons.
        """

        self.back_button.clicked.connect(self._go_back)
        self.song_combo.currentIndexChanged.connect(self._select_song)
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.start_button.clicked.connect(self.start_input)
        self.target_view_button.clicked.connect(self._show_target_panel)
        self.tracks_view_button.clicked.connect(self._show_tracks_panel)
        self.transpose_spin.valueChanged.connect(self._set_transpose)
        self.transpose_down_button.clicked.connect(self._decrement_transpose)
        self.transpose_up_button.clicked.connect(self._increment_transpose)
        self.play_pause_button.clicked.connect(self.toggle_playback)
        self.restart_button.clicked.connect(self.restart_playback)
        self.speed_combo.currentIndexChanged.connect(self._set_play_speed)
        self.timeline_overview.playhead_changed.connect(self._seek_playhead)

    def _decrement_transpose(self) -> None:
        """Move the Play chart transpose down by one semitone.

        The buttons are a compact UI adapter over the same bounded transpose
        policy as the spin box; the scored chart remains selected track plus
        clamped semitone offset.

        @author Codex - added explicit Play transpose decrement control.
        """

        self.transpose_spin.setValue(clamp_transpose(self._transpose_semitones - 1))

    def _increment_transpose(self) -> None:
        """Move the Play chart transpose up by one semitone.

        The buttons are a compact UI adapter over the same bounded transpose
        policy as the spin box; the scored chart remains selected track plus
        clamped semitone offset.

        @author Codex - added explicit Play transpose increment control.
        """

        self.transpose_spin.setValue(clamp_transpose(self._transpose_semitones + 1))

    def _show_target_panel(self) -> None:
        """Show target and feedback readouts in the side rail.

        The choice is purely a workspace layout concern. It does not alter the
        selected MIDI track or Play scoring state.

        @author Codex - added side-rail view switcher for target status versus tracks.
        """

        self.side_stack.setCurrentIndex(0)
        self.target_view_button.setChecked(True)
        self.tracks_view_button.setChecked(False)

    def _show_tracks_panel(self) -> None:
        """Show MIDI track controls in the side rail.

        Track controls are kept one click away so target feedback has enough
        space while practicing without hiding track selection entirely.

        @author Codex - added side-rail view switcher for target status versus tracks.
        """

        self.side_stack.setCurrentIndex(1)
        self.target_view_button.setChecked(False)
        self.tracks_view_button.setChecked(True)

    def _update_input_button(self) -> None:
        """Render live input as record/stop transport symbology.

        A red record circle means start capture; a square means stop. Using a
        play triangle here would suggest MIDI playback, while this control owns
        the microphone/input stream.

        @author Codex - replaced Play input text with standard capture symbols.
        """

        if self._running:
            self.start_button.setText("")
            self.start_button.setAccessibleName("Stop input")
            self.start_button.setToolTip("Stop input")
            self.start_button.setProperty("inputState", "running")
        else:
            self.start_button.setText("")
            self.start_button.setAccessibleName("Start input")
            self.start_button.setToolTip("Start input")
            self.start_button.setProperty("inputState", "stopped")
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)

    def refresh_devices(self) -> None:
        """Reload available input devices for Play's live detector.

        This mirrors Sandbox's working input boundary. Play does not auto-open
        a hidden stream from its constructor; activation owns that resource.

        @author Codex - aligned Play input device selection with Sandbox.
        """

        self._devices = list_input_devices()
        self.device_combo.clear()
        for device in self._devices:
            self.device_combo.addItem(
                f"[{device.index}] {device.name} ({device.input_channels} in, {device.default_sample_rate} Hz)",
                device.index,
            )
        codec_index = next(
            (index for index, device in enumerate(self._devices) if "codec" in device.name.casefold()),
            -1,
        )
        if codec_index >= 0:
            self.device_combo.setCurrentIndex(codec_index)
        self.start_button.setEnabled(bool(self._devices))
        self.status_label.setText("No input devices found." if not self._devices else "Ready.")
        dump(
            "play",
            "devices_refreshed",
            count=len(self._devices),
            devices=[
                {
                    "index": device.index,
                    "name": device.name,
                    "inputs": device.input_channels,
                    "sample_rate": device.default_sample_rate,
                }
                for device in self._devices
            ],
            selected=self.device_combo.currentData(),
        )

    def start_input(self) -> None:
        """Start live capture from the selected device.

        @author Codex - aligned Play input start behavior with Sandbox.
        """

        if self._running:
            dump("play", "input_toggle_stop")
            self.stop_input()
            return
        device_index = self.device_combo.currentData()
        if device_index is None:
            self.status_label.setText("No input device selected.")
            dump("play", "input_start_blocked", reason="no_device")
            return
        try:
            dump("play", "input_start_requested", device_index=device_index)
            self._input.start(int(device_index))
        except Exception as exc:
            self.status_label.setText(f"Could not open input: {exc}")
            dump("play", "input_start_failed", device_index=device_index, error=str(exc))
            return
        self._running = True
        self._pluck_detector.reset()
        self._update_input_button()
        self.sample_rate_label.setText(f"Sample rate: {self._input.sample_rate} Hz")
        self.status_label.setText("Listening.")
        self._frame_count = 0
        self._last_readout_at = 0.0
        self._timer.start()
        dump("play", "input_started", device_index=device_index, sample_rate=self._input.sample_rate)

    def stop_input(self) -> None:
        """Stop live capture and leave the last Play readout visible.

        @author Codex - aligned Play input stop behavior with Sandbox.
        """

        self._input.stop()
        self._running = False
        self._update_input_button()
        self.status_label.setText("Stopped.")
        self._sync_timer()
        dump("play", "input_stopped")

    def toggle_playback(self) -> None:
        """Toggle Play's song clock without changing microphone capture.

        @author Codex - added Play play/pause control with resume count-in.
        """

        state = self._controller.update(time.monotonic())
        if state.is_running:
            state = self._controller.pause(time.monotonic())
            self.status_label.setText("Paused.")
            dump("play", "playback_paused", state=_state_dump(state))
        else:
            state = self._controller.start(time.monotonic())
            self.status_label.setText("Playing." if not state.is_running else "Get ready.")
            dump("play", "playback_started", state=_state_dump(state))
        self._render_state(state)
        self._sync_timer()

    def restart_playback(self) -> None:
        """Restart Play from the beginning of the selected song region.

        @author Codex - added Play restart control.
        """

        state = self._controller.restart()
        self.status_label.setText("Restarted.")
        dump("play", "playback_restarted", state=_state_dump(state))
        self._render_state(state)
        self._sync_timer()

    def _set_play_speed(self, index: int) -> None:
        """Apply the selected Play speed to the controller clock.

        Speed is a Play timing policy, not a piano-roll rendering concern, so
        the widget only forwards the selected multiplier into the controller.

        @author Codex - added Play speed control adapter.
        """

        multiplier = self.speed_combo.itemData(index)
        if multiplier is None:
            return
        state = self._controller.set_speed_multiplier(float(multiplier), now=time.monotonic())
        dump("play", "speed_changed", speed=state.speed_multiplier, state=_state_dump(state))
        self._render_state(state)

    def _seek_playhead(self, playhead_time: float) -> None:
        """Move Play to a user-selected overview playhead position.

        @author Codex - added draggable Play overview start position.
        """

        state = self._controller.seek(playhead_time)
        self.status_label.setText(f"Start: {state.playhead_time:.1f}s")
        dump("play", "playhead_seeked", state=_state_dump(state))
        self._render_state(state)
        self._sync_timer()

    def _sync_timer(self) -> None:
        """Run the shared UI timer while input or playback needs updates.

        @author Codex - added Play play/pause control with resume count-in.
        """

        if self._running or self._controller.snapshot().is_running:
            if not self._timer.isActive():
                self._timer.start()
            return
        if self._timer.isActive():
            self._timer.stop()

    def _update_playback_button(self, state: object) -> None:
        """Reflect Play clock state in the play/pause control.

        @author Codex - added Play play/pause control with resume count-in.
        """

        is_running = bool(getattr(state, "is_running", False))
        self.play_pause_button.setText("||" if is_running else ">")
        self.play_pause_button.setAccessibleName("Pause" if is_running else "Play")
        self.play_pause_button.setToolTip("Pause music" if is_running else "Play from the current song position")

    def _load_songs(self) -> None:
        """Load bundled MIDI songs and the fallback demo.

        @author Codex - created Play song loading.
        """

        self.song_combo.blockSignals(True)
        self.song_combo.clear()
        self._songs = []
        errors: list[str] = []

        for midi_path in discover_midi_songs(PROJECT_ROOT):
            try:
                self._songs.append(load_midi_song(midi_path))
            except Exception as exc:
                errors.append(f"{midi_path.name}: {exc}")

        self._songs.append(demo_song())
        for song in self._songs:
            source = "demo" if song.is_demo else (song.path.name if song.path else "built-in")
            self.song_combo.addItem(f"{song.title} [{source}]", song)

        self.song_combo.blockSignals(False)
        if self._songs:
            self.song_combo.setCurrentIndex(0)
            self._select_song(0)
        if errors and len(self._songs) == 1:
            self.status_label.setText(f"Using demo targets. MIDI error: {errors[0]}")
        dump(
            "play",
            "songs_loaded",
            count=len(self._songs),
            songs=[song.title for song in self._songs],
            errors=errors,
        )

    def _select_song(self, index: int) -> None:
        """Load the song and rebuild manual track controls.

        @author Codex - created explicit Play track-choice behavior.
        @author Codex - replaced track combo with piano-roll track panel.
        @author Codex - reset Play MIDI overview to the locked lookahead window.
        @author Codex - selected an obvious guitar track by default for multi-track MIDI.
        @author Codex - reset the dedicated Play playhead bar on song changes.
        """

        song = self.song_combo.itemData(index)
        self._current_song = song if isinstance(song, PlaySong) else None
        self._target_track = None
        self._track_states = {}
        self._clear_track_rows()

        if self._current_song is None:
            self._controller.clear_section()
            self.timeline_overview.set_song(None)
            self.timeline.set_song(None)
            self.timeline.set_transpose(self._transpose_semitones)
            self._update_transpose_readouts()
            self._render_state()
            dump("play", "song_selected", index=index, valid=False)
            return

        for track in self._current_song.tracks:
            self._track_states[track.index] = TrackUiState()
            self._add_track_row(track)
        self.track_list.addStretch(1)
        display_window = self._lookahead_window(self._current_song.start_time)
        self.timeline_overview.set_song(self._current_song, display_window)
        self.timeline.set_song(self._current_song)
        self.timeline.set_transpose(self._transpose_semitones)
        self.timeline.set_visible_tracks(self._visible_track_indexes())

        default_track = self._default_target_track()
        if default_track is not None:
            self._select_target_track(default_track.index)
        elif self._current_song.requires_track_choice:
            self._controller.clear_section()
            self.status_label.setText("Choose a target track. Visibility and audibility can be changed independently.")
        elif self._current_song.tracks:
            self._select_target_track(self._current_song.tracks[0].index)
        self._render_state()
        dump(
            "play",
            "song_selected",
            index=index,
            title=self._current_song.title,
            path=self._current_song.path,
            tracks=[
                {
                    "index": track.index,
                    "name": track.name,
                    "targets": len(track.section.targets),
                    "notes": track.note_count,
                    "range": self._range_text(note_range_for_targets(track.section.targets, original=True)),
                }
                for track in self._current_song.tracks
            ],
            requires_track_choice=self._current_song.requires_track_choice,
        )

    def _clear_track_rows(self) -> None:
        """Remove track controls for the previous song.

        @author Codex - added Play track panel lifecycle.
        """

        while self.track_list.count():
            item = self.track_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._track_rows = {}
        self._track_detail_labels = {}
        self._target_radios = {}
        self.target_group = QButtonGroup(self)
        self.target_group.setExclusive(True)

    def _add_track_row(self, track: MidiTrackOption) -> None:
        """Create controls for one MIDI track.

        @author Codex - added Play track panel controls.
        """

        row = QFrame()
        row.setObjectName("trackRow")
        layout = QGridLayout(row)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)

        swatch = QLabel()
        swatch.setObjectName("trackSwatch")
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"background: {track.color}; border-radius: 3px;")
        target_radio = QRadioButton("Target")
        target_radio.toggled.connect(lambda checked, index=track.index: checked and self._select_target_track(index))
        self.target_group.addButton(target_radio)
        self._target_radios[track.index] = target_radio
        visible_check = QCheckBox("Visible")
        visible_check.setChecked(True)
        visible_check.toggled.connect(lambda checked, index=track.index: self._set_track_visible(index, checked))

        title = QLabel(track.name)
        title.setObjectName("trackName")
        title.setWordWrap(True)
        details = QLabel(self._track_details(track))
        details.setObjectName("trackDetails")
        details.setWordWrap(True)
        self._track_detail_labels[track.index] = details

        layout.addWidget(swatch, 0, 0)
        layout.addWidget(title, 0, 1, 1, 3)
        layout.addWidget(details, 1, 1, 1, 3)
        layout.addWidget(target_radio, 2, 0, 1, 2)
        layout.addWidget(visible_check, 3, 0, 1, 2)
        self.track_list.addWidget(row)
        self._track_rows[track.index] = row

    def _default_target_track(self) -> MidiTrackOption | None:
        """Return a clear guitar target candidate for multi-track MIDI.

        Multi-track files should not default to the first arbitrary instrument,
        but a track explicitly named as guitar is strong enough UI context to
        avoid making guitar MIDIs feel broken on load.

        @author Codex - selected an obvious guitar track by default for multi-track MIDI.
        """

        if self._current_song is None or not self._current_song.requires_track_choice:
            return None
        return next(
            (
                track
                for track in self._current_song.tracks
                if "guitar" in " ".join((track.name, *track.instrument_labels)).casefold()
            ),
            None,
        )

    def _track_details(self, track: MidiTrackOption) -> str:
        """Return compact metadata shown in a track row.

        @author Codex - added Play track panel metadata.
        """

        parts = [f"{track.note_count} notes", f"{len(track.section.targets)} targets"]
        original_range = self._range_text(note_range_for_targets(track.section.targets, original=True))
        if original_range:
            parts.append(f"Original range: {original_range}")
        if self._target_track is not None and track.index == self._target_track.index:
            transposed_targets = apply_transpose(track.section.targets, self._transpose_semitones)
            transposed_range = self._range_text(note_range_for_targets(transposed_targets))
            if transposed_range:
                parts.append(f"Transposed range: {transposed_range}")
            parts.append(f"Transpose: {self._signed_transpose(self._transpose_semitones)}")
        if track.channel_labels:
            parts.append(f"ch {','.join(track.channel_labels)}")
        if track.instrument_labels:
            parts.append(", ".join(track.instrument_labels))
        return " | ".join(parts)

    def _refresh_track_details(self) -> None:
        """Refresh track metadata affected by target-track transposition.

        @author Codex - added Play transpose metadata refresh.
        """

        if self._current_song is None:
            return
        for track in self._current_song.tracks:
            label = self._track_detail_labels.get(track.index)
            if label is not None:
                label.setText(self._track_details(track))

    def _find_track(self, track_index: int) -> MidiTrackOption | None:
        """Return the current song track by MIDI index.

        @author Codex - added Play track lookup helper.
        """

        if self._current_song is None:
            return None
        return next((track for track in self._current_song.tracks if track.index == track_index), None)

    def _select_target_track(self, track_index: int) -> None:
        """Load one track as the only source of Play targets.

        Other tracks remain available as visible context. The
        section passed to the controller uses song-wide bounds so region handles
        can select accompaniment context wider than the target track's notes.

        @author Codex - updated explicit Play track-choice behavior.
        """

        track = self._find_track(track_index)
        if track is None or self._current_song is None:
            self._controller.clear_section()
            self.status_label.setText("Choose a target track to score.")
            self._render_state()
            return

        self._target_track = track
        radio = self._target_radios.get(track.index)
        if radio is not None and not radio.isChecked():
            radio.setChecked(True)
        section = self._section_for_target_track(track)
        state = self._controller.set_section(section)
        self.timeline.set_target_track(track.index)
        self.timeline.set_transpose(self._transpose_semitones)
        self.status_label.setText(f"Target track: {track.name}. Context tracks can stay visible.")
        dump(
            "play",
            "target_track_selected",
            track_index=track.index,
            track_name=track.name,
            transpose=self._transpose_semitones,
            current_target=_target_dump(state.current_target),
            bounds={
                "start": self._controller.region.start_time,
                "end": self._controller.region.end_time,
            },
        )
        self._refresh_track_details()
        self._update_transpose_readouts()
        self._render_state(state)

    def _section_for_target_track(self, track: MidiTrackOption) -> PlaySection:
        """Return the active Play section for selected track plus transpose.

        The source track section remains raw MIDI. The returned section is the
        Play chart, where pitch expectations reflect the current user
        correction while song timing stays unchanged.

        @author Codex - added Play chart transposition section builder.
        """

        if self._current_song is None:
            return transpose_section(track.section, self._transpose_semitones)
        return PlaySection(
            start_time=self._current_song.start_time,
            end_time=self._current_song.end_time,
            targets=apply_transpose(track.section.targets, self._transpose_semitones),
        )

    def _set_track_visible(self, track_index: int, visible: bool) -> None:
        """Apply timeline visibility.

        @author Codex - added Play track visibility behavior.
        @author Codex - removed Play Run Mode playback controls.
        """

        state = self._track_states.get(track_index)
        if state is None:
            return
        state.visible = bool(visible)
        self.timeline.set_visible_tracks(self._visible_track_indexes())
        dump("play", "track_visible_changed", track_index=track_index, visible=visible)

    def _visible_track_indexes(self) -> frozenset[int]:
        """Return track indexes currently visible on the piano roll.

        @author Codex - added Play track visibility behavior.
        """

        return frozenset(index for index, state in self._track_states.items() if state.visible)

    def _set_transpose(self, semitones: int) -> None:
        """Apply user semitone transposition to the Play chart only.

        This rebuilds expected targets from the raw selected track so repeated
        changes never stack offsets onto already-transposed notes. MIDI source
        data, note timing, durations, and selected region
        are left untouched.

        @author Codex - added Play transpose UI behavior.
        @author Codex - removed Play Run Mode playback controls.
        """

        self._transpose_semitones = clamp_transpose(semitones)
        self.timeline.set_transpose(self._transpose_semitones)
        state = None
        if self._target_track is not None:
            state = self._controller.set_section(
                self._section_for_target_track(self._target_track),
                preserve_region=True,
            )
        expected = state.current_target.midi_notes if state is not None and state.current_target is not None else []
        dump(
            "play",
            "transpose_changed",
            transpose=self._transpose_semitones,
            expected=expected,
            current_target=_target_dump(state.current_target if state is not None else None),
        )
        self._refresh_track_details()
        self._update_transpose_readouts()
        self._render_state(state)

    def _sync_locked_display_window(self, playhead_time: float) -> None:
        """Keep Play focused on the next fixed-size slice of the song.

        Play is the performance surface, so the chart viewport follows the
        current musical position instead of exposing manual navigation handles.
        The 15-second lookahead is UI policy; it does not alter the scoring
        bounds consumed by ``PlayController``.

        @author Codex - locked Play overview to the next 15 seconds.
        """

        if self._current_song is None:
            return
        window = self._lookahead_window(playhead_time)
        self.timeline_overview.set_display_window(window.start_time, window.end_time)
        self.timeline.set_display_window(window.start_time, window.end_time)

    def _lookahead_window(self, playhead_time: float) -> TimeRegion:
        """Return the locked 15-second Play viewport at ``playhead_time``.

        @author Codex - locked Play overview to the next 15 seconds.
        """

        if self._current_song is None:
            return TimeRegion(0.0, 0.0)
        start_time = max(self._current_song.start_time, min(playhead_time, self._current_song.end_time))
        end_time = min(start_time + PLAY_LOOKAHEAD_SECONDS, self._current_song.end_time)
        if end_time - start_time < PLAY_LOOKAHEAD_SECONDS:
            start_time = max(self._current_song.start_time, end_time - PLAY_LOOKAHEAD_SECONDS)
        return TimeRegion(start_time, end_time).clamp(
            self._current_song.start_time,
            self._current_song.end_time,
            minimum_duration=min(PLAY_LOOKAHEAD_SECONDS, max(self._current_song.end_time - self._current_song.start_time, 0.0)),
        )

    def _update_frame(self) -> None:
        """Advance playback and read the newest live input frame.

        @author Codex - aligned Play input polling with Sandbox.
        @author Codex - added Play play/pause control with resume count-in.
        """

        state = self._controller.update(time.monotonic())
        self._render_state(state)
        frame = self._input.latest_frame()
        if frame is None:
            self._sync_timer()
            return
        self._render_frame(frame)
        self._sync_timer()

    def _render_frame(self, frame: PitchFrame) -> None:
        """Render one live detector frame into Play scoring state.

        Play shows the live pitch estimate immediately, borrowing Sandbox's
        frame-level readout. A classified pluck still owns target matching so
        transient frame noise does not advance scoring.

        @author Codex - created Play detector integration.
        @author Codex - aligned Play frame rendering with Sandbox.
        @author Codex - added realtime Play detected-note readout.
        @author Codex - removed Play Run Mode play/pause gating.
        """

        self._remember_live_frame_note(frame)
        pluck = self._pluck_detector.process_frame(frame, time.monotonic())
        if pluck is not None:
            self._remember_detected_note(pluck.midi)
            state = self._controller.snapshot()
            expected = state.current_target.midi_notes if state.current_target is not None else []
            dump(
                "play",
                "pluck",
                note=pluck.note_name,
                midi=pluck.midi,
                confidence=pluck.confidence,
                running=state.is_running,
                expected=expected,
                current_target=_target_dump(state.current_target),
                likely_peak=_peak_dump(frame.likely_fundamental),
                dominant_peak=_peak_dump(frame.dominant_peak),
            )
            if state.current_target is not None:
                state = self._controller.process_detected_note(pluck.midi, confidence=pluck.confidence, now=time.monotonic())
                dump("play", "match_result", state=_state_dump(state))
                self.status_label.setText(f"Detected {pluck.note_name}.")
                self._render_state(state)
            else:
                self.status_label.setText(f"Detected {pluck.note_name}. Choose a target track to score.")
                self._render_state()
        else:
            self.status_label.setText("Listening.")
        self._frame_count += 1
        self._last_readout_at = time.monotonic()
        if self._last_readout_at - getattr(self, "_last_frame_dump_at", 0.0) >= 0.75:
            self._last_frame_dump_at = self._last_readout_at
            state = self._controller.snapshot()
            dump(
                "play",
                "frame",
                frame_count=self._frame_count,
                rms=getattr(frame, "rms", None),
                confidence=getattr(frame, "confidence", None),
                reason=getattr(frame, "reason", None),
                likely_peak=_peak_dump(frame.likely_fundamental),
                dominant_peak=_peak_dump(frame.dominant_peak),
                running=state.is_running,
                current_target=_target_dump(state.current_target),
            )

    def _remember_live_frame_note(self, frame: PitchFrame) -> None:
        """Update the Play detected-note panel from the current FFT frame.

        This is display-only. The controller still consumes pluck events, but
        the user can see the incoming note estimate immediately like in
        Sandbox.

        @author Codex - added realtime Play detected-note readout.
        """

        peak = self._live_peak_for_frame(frame)
        if peak is None:
            return
        self._remember_detected_note(peak.midi)
        self.detected_label.setText(self._detected_text(self._latest_detected_notes))

    def _live_peak_for_frame(self, frame: PitchFrame) -> SpectrumPeak | None:
        """Return the frame-level pitch estimate Play should display.

        The priority mirrors Sandbox's spectrum marker: use the analyzed likely
        fundamental, then a peak tagged as fundamental, then the dominant peak.

        @author Codex - added realtime Play detected-note readout.
        """

        if frame.likely_fundamental is not None:
            return frame.likely_fundamental
        fundamentals = [peak for peak in frame.peaks if peak.harmonic_relationship == "fundamental"]
        if fundamentals:
            return min(fundamentals, key=lambda peak: peak.frequency_hz)
        return frame.dominant_peak or (frame.peaks[0] if frame.peaks else None)

    def _remember_detected_note(self, midi_note: int) -> None:
        """Keep a live detected-note readout independent from scoring state.

        The screen needs to prove that live input is reaching the detector even
        before a target track is selected.

        @author Codex - added Play paused detection readout.
        @author Codex - removed Play Run Mode play/pause gating.
        """

        note = int(midi_note)
        previous = tuple(existing for existing in self._latest_detected_notes if existing != note)
        self._latest_detected_notes = (previous + (note,))[-8:]

    def _render_state(self, state: object | None = None) -> None:
        """Render a controller state snapshot into Play widgets.

        @author Codex - created Play UI state rendering.
        @author Codex - updated Play UI rendering for piano roll.
        @author Codex - removed Play Run Mode HUD state.
        """

        state = state or self._controller.snapshot()
        self._sync_locked_display_window(state.playhead_time)
        self.timeline_overview.set_playhead(state.playhead_time)
        self.timeline.set_state(
            current_target=state.current_target,
            passed_indexes=state.passed_target_indexes,
            missed_indexes=state.missed_target_indexes,
        )
        if state.current_target is None:
            self.current_target_label.setText("--")
            self.expected_label.setText("Choose a target track to generate Play targets.")
        else:
            self.current_target_label.setText(self._target_title(state.current_target))
            self.expected_label.setText(self._expected_text(state.current_target, set(state.matched_notes)))

        detected_notes = self._latest_detected_notes or state.detected_notes
        self.detected_label.setText(self._detected_text(detected_notes))
        self.progress_label.setText(
            f"{state.passed_count} / {state.selected_count} passed"
            + (f" | {state.missed_count} miss" if state.missed_count == 1 else f" | {state.missed_count} misses")
        )
        self.hit_count_label.setText(str(state.passed_count))
        self.miss_count_label.setText(str(state.missed_count))
        count_in_remaining = getattr(state, "count_in_remaining", 0.0)
        if count_in_remaining > 0:
            self.feedback_label.setText(str(max(1, int(count_in_remaining + 0.999))))
            self._set_feedback_color(None)
        else:
            self.feedback_label.setText(state.feedback.value)
            self._set_feedback_color(state.feedback)
        self._update_transpose_readouts()
        self._update_playback_button(state)

    def _expected_text(self, target: PlayTarget, matched_notes: set[int]) -> str:
        """Return checklist text for the current target.

        @author Codex - created Play target checklist rendering.
        @author Codex - added desired target frequencies to Play.
        """

        lines = ["Expected:"]
        for midi_note in target.midi_notes:
            marker = "[x]" if midi_note in matched_notes else "[ ]"
            lines.append(f"{marker} {self._desired_note_text(midi_note)}")
        return "\n".join(lines)

    def _target_title(self, target: PlayTarget) -> str:
        """Return the current target label with desired note frequencies.

        @author Codex - added desired target frequencies to Play.
        """

        return " + ".join(self._desired_note_text(midi_note) for midi_note in target.midi_notes)

    def _desired_note_text(self, midi_note: int) -> str:
        """Return a desired MIDI note as note name plus equal-tempered Hz.

        @author Codex - added desired target frequencies to Play.
        """

        return f"{midi_note_name(midi_note)} ({note_to_frequency(midi_note):.1f} Hz)"

    def _detected_text(self, detected_notes: tuple[int, ...]) -> str:
        """Return detected-note text for the status panel.

        @author Codex - created Play detected-note rendering.
        """

        if not detected_notes:
            return "Detected: --"
        names = ", ".join(midi_note_name(note) for note in detected_notes[-8:])
        return f"Detected: {names}"

    def _update_transpose_readouts(self) -> None:
        """Refresh transpose preview and guitar-range diagnostics.

        @author Codex - added Play transpose preview and range warnings.
        @author Codex - compacted Play transpose preview text for the toolbar.
        @author Codex - refreshed segmented transpose stepper value.
        """

        signed = self._signed_transpose(self._transpose_semitones)
        self.transpose_value_label.setText(signed)
        if self._target_track is None:
            self.transpose_preview_label.setText(f"Transpose: {signed} st")
            self.lowest_note_label.setText("Lowest note: --")
            self.highest_note_label.setText("Highest note: --")
            self._set_range_label_state(self.lowest_note_label, warning=False)
            self._set_range_label_state(self.highest_note_label, warning=False)
            self.range_warning_label.setText("")
            return

        original_range = note_range_for_targets(self._target_track.section.targets, original=True)
        transposed_targets = apply_transpose(self._target_track.section.targets, self._transpose_semitones)
        transposed_range = note_range_for_targets(transposed_targets)
        if original_range is None or transposed_range is None:
            self.transpose_preview_label.setText(f"Transpose: {signed} st")
            self.lowest_note_label.setText("Lowest note: --")
            self.highest_note_label.setText("Highest note: --")
            self._set_range_label_state(self.lowest_note_label, warning=False)
            self._set_range_label_state(self.highest_note_label, warning=False)
            self.range_warning_label.setText("")
            return

        if original_range[0] == original_range[1]:
            preview = (
                f"Transpose: {signed} st | "
                f"{midi_note_name(original_range[0])} -> {midi_note_name(transposed_range[0])}"
            )
        else:
            preview = (
                f"Range: {midi_note_name(original_range[0])}-{midi_note_name(original_range[1])}"
                f" -> {midi_note_name(transposed_range[0])}-{midi_note_name(transposed_range[1])}"
            )
        self.transpose_preview_label.setText(preview)
        self.lowest_note_label.setText(f"Lowest note: {midi_note_name(transposed_range[0])}")
        self.highest_note_label.setText(f"Highest note: {midi_note_name(transposed_range[1])}")

        validation = validate_guitar_range(transposed_targets)
        self._set_range_label_state(self.lowest_note_label, warning=validation.has_below_range_notes)
        self._set_range_label_state(self.highest_note_label, warning=validation.has_above_range_notes)
        self.range_warning_label.setText("")

    def _set_range_label_state(self, label: QLabel, *, warning: bool) -> None:
        """Render a transpose range readout as normal or out-of-range.

        Play keeps the guitar-range policy in ``validate_guitar_range``. The
        Qt adapter only maps that result to a compact visual warning so the
        range section stays scannable while practicing.

        @author Codex - rendered transpose range warnings as label state.
        """

        label.setProperty("rangeState", "warning" if warning else "normal")
        label.style().unpolish(label)
        label.style().polish(label)

    def _range_text(self, note_range: tuple[int, int] | None) -> str:
        """Return a compact note range for track metadata.

        @author Codex - added Play transpose range text.
        """

        if note_range is None:
            return ""
        low, high = note_range
        if low == high:
            return midi_note_name(low)
        return f"{midi_note_name(low)} - {midi_note_name(high)}"

    def _signed_transpose(self, semitones: int) -> str:
        """Return a transpose value with an explicit plus sign when needed.

        @author Codex - added Play transpose display formatting.
        """

        value = int(semitones)
        return f"+{value}" if value > 0 else str(value)

    def _set_feedback_color(self, feedback: Feedback | None) -> None:
        """Style the feedback readout for the active state.

        @author Codex - created Play feedback rendering.
        @author Codex - mapped Play countdown and feedback colors.
        """

        color = {
            None: "#ffd43b",
            Feedback.IDLE: "#9aa4b2",
            Feedback.MISS: "#ff4d4d",
            Feedback.GOOD: "#3ddc84",
            Feedback.PERFECT: "#21d4fd",
        }.get(feedback, "#f5f5f5")
        self.feedback_label.setStyleSheet(f"color: {color};")

    def _go_back(self) -> None:
        """Leave Play and release its resources.

        @author Codex - created Play back navigation.
        """

        self.deactivate()
        self.back_requested.emit()

    def _apply_style(self) -> None:
        """Apply Play screen styling.

        @author Codex - created first Play mode screen.
        @author Codex - added piano-roll and track panel styling.
        @author Codex - removed Play Run Mode controls.
        @author Codex - tightened Play toolbar control spacing.
        @author Codex - styled Play transpose as a compact grouped control.
        @author Codex - styled Play transpose segmented stepper model.
        """

        self.setStyleSheet(
            """
            QWidget {
                background: #0b0b0b;
                color: #f5f5f5;
                font-family: Inter, Segoe UI, Arial, sans-serif;
                font-size: 13px;
            }
            #title {
                color: #ff4d4d;
                font-size: 24px;
                font-weight: 800;
            }
            #panel, #infoPanel, #trackPanel, #timelineOverviewPanel, #pianoRollPanel {
                background: #141414;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
            }
            #timelineOverviewPanel, #pianoRollPanel {
                padding: 0;
            }
            #trackPanel {
                border: 0;
            }
            #transposePanel {
                background: #181818;
                border: 1px solid #303030;
                border-radius: 8px;
            }
            #transposeTitle {
                background: transparent;
                color: #b8b8b8;
                font-weight: 800;
            }
            #transposePreview {
                background: transparent;
                color: #d8e2ef;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 14px;
            }
            #trackRow {
                background: #181818;
                border: 1px solid #303030;
                border-radius: 8px;
            }
            #trackName {
                color: #f5f5f5;
                font-weight: 800;
            }
            #trackDetails {
                color: #9fb0c5;
                font-size: 12px;
            }
            #sectionTitle {
                color: #b8b8b8;
                font-weight: 800;
            }
            #status {
                color: #b8c7dc;
            }
            QPushButton, QComboBox, QSpinBox {
                background: #181818;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #f5f5f5;
                padding: 5px 8px;
            }
            QPushButton:hover, QComboBox:hover, QSpinBox:hover {
                border-color: #ff4d4d;
            }
            #inputDeviceCombo, #refreshDevicesButton {
                padding: 7px 9px;
            }
            QPushButton:checked {
                background: #2a1b1b;
                border-color: #ff4d4d;
            }
            #inputToggleButton {
                min-width: 34px;
                max-width: 34px;
                min-height: 34px;
                max-height: 34px;
                border-radius: 17px;
                padding: 0;
                background: #ff3b30;
                border: 0;
            }
            #inputToggleButton:hover {
                background: #ff5a52;
                border: 0;
            }
            #inputToggleButton[inputState="running"] {
                border-radius: 4px;
                background: #f5f5f5;
                border: 0;
            }
            #inputToggleButton[inputState="running"]:hover {
                background: #ffffff;
                border: 0;
            }
            #playPauseButton, #restartButton {
                min-width: 44px;
                max-width: 44px;
                min-height: 38px;
                max-height: 38px;
                font-weight: 800;
                font-size: 18px;
                padding: 0;
                text-align: center;
            }
            #playPauseButton {
                background: #21d4fd;
                border-color: #21d4fd;
                color: #05070a;
            }
            #restartButton {
                background: #202020;
                border-color: #404040;
            }
            #hitCount {
                color: #3ddc84;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 22px;
                font-weight: 900;
                min-width: 30px;
            }
            #missCount {
                color: #ff4d4d;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 22px;
                font-weight: 900;
                min-width: 30px;
            }
            #transposeStepDown, #transposeStepUp {
                min-width: 38px;
                max-width: 38px;
                min-height: 36px;
                max-height: 36px;
                border-radius: 7px;
                padding: 0;
                background: #1f1f1f;
                border: 1px solid #333333;
                color: #ffffff;
                font-size: 21px;
                font-weight: 900;
                text-align: center;
            }
            #transposeStepDown:hover, #transposeStepUp:hover {
                background: #ff3b30;
                border-color: #ff3b30;
            }
            #transposeValue {
                min-width: 62px;
                max-width: 62px;
                min-height: 36px;
                max-height: 36px;
                background: #121212;
                border: 1px solid #333333;
                border-radius: 7px;
                color: #21d4fd;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 14px;
                font-weight: 900;
            }
            QCheckBox, QRadioButton {
                spacing: 6px;
            }
            #targetName {
                color: #21d4fd;
                font-size: 36px;
                font-weight: 900;
            }
            #feedback {
                font-size: 44px;
                font-weight: 900;
                background: #080b10;
                border: 1px solid #25344a;
                border-radius: 8px;
                padding: 14px;
            }
            #monoText {
                color: #d8e2ef;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 14px;
            }
            #rangeText {
                background: transparent;
                color: #b8c7dc;
                font-size: 12px;
            }
            #rangeText[rangeState="warning"] {
                color: #ff4d4d;
                font-weight: 800;
            }
            """
        )
def _peak_dump(peak: SpectrumPeak | None) -> dict[str, object] | None:
    """Return compact pitch-peak data for terminal diagnostics.

    @author Codex - added Play terminal debug dump.
    """

    if peak is None:
        return None
    return {
        "note": midi_note_name(peak.midi),
        "midi": peak.midi,
        "hz": round(peak.frequency_hz, 3),
        "percent": round(getattr(peak, "relative_percent", 0.0), 2),
        "relationship": getattr(peak, "harmonic_relationship", None),
    }


def _target_dump(target: PlayTarget | None) -> dict[str, object] | None:
    """Return active target data needed to debug Play matching.

    @author Codex - added Play terminal debug dump.
    """

    if target is None:
        return None
    return {
        "label": target.label,
        "original": target.original_midi_notes,
        "expected": target.midi_notes,
        "expected_names": [midi_note_name(note) for note in target.midi_notes],
        "start": target.start_time,
        "end": target.end_time,
    }


def _state_dump(state: object) -> dict[str, object]:
    """Return compact controller state for terminal diagnostics.

    @author Codex - added Play terminal debug dump.
    """

    return {
        "feedback": getattr(state, "feedback", None),
        "running": getattr(state, "is_running", None),
        "index": getattr(state, "current_index", None),
        "playhead": getattr(state, "playhead_time", None),
        "selected": getattr(state, "selected_count", None),
        "passed": getattr(state, "passed_count", None),
        "missed": getattr(state, "missed_count", None),
        "detected": list(getattr(state, "detected_notes", ())),
        "matched": list(getattr(state, "matched_notes", ())),
        "missing": list(getattr(state, "missing_notes", ())),
        "current_target": _target_dump(getattr(state, "current_target", None)),
    }
