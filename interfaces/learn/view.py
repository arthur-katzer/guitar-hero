"""Qt adapter for Learn mode."""

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
from interfaces.learn.controller import LearnController
from interfaces.learn.midi_targets import demo_song, discover_midi_songs, load_midi_song, midi_note_name
from interfaces.learn.model import (
    Feedback,
    LearnSection,
    LearnSong,
    LearnTarget,
    MidiTrackOption,
    PracticeRegion,
)
from interfaces.learn.transposition import (
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


@dataclass
class TrackUiState:
    """Mutable Qt-side controls for one loaded MIDI track.

    Visibility is a display-only control. Keeping it outside
    ``LearnController`` prevents chart context from becoming target-generation
    policy.

    @author Codex - added Learn piano-roll track UI state.
    @author Codex - removed Learn Run Mode playback state.
    """

    visible: bool = True


class MidiOverviewBar(QWidget):
    """Full-song MIDI overview with draggable visible-window handles.

    The overview is a Qt navigation adapter, not practice policy. It owns the
    display window shown by ``PianoRollTimeline`` while Learn target selection
    and practice-region timing remain in ``LearnController``.

    @author Codex - added Learn MIDI overview viewport control.
    """

    display_window_changed = Signal(float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(72)
        self.setMaximumHeight(82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._song: LearnSong | None = None
        self._display_window = PracticeRegion(0.0, 0.0)
        self._dragging: str | None = None
        self._drag_start_x = 0
        self._drag_start_window = PracticeRegion(0.0, 0.0)

    def set_song(self, song: LearnSong | None, window: PracticeRegion | None = None) -> None:
        """Load the full MIDI bounds represented by the overview bar.

        @author Codex - added Learn MIDI overview viewport control.
        """

        self._song = song
        if song is None:
            self._display_window = PracticeRegion(0.0, 0.0)
        else:
            self._display_window = self._clamp_window(
                window or PracticeRegion(song.start_time, song.end_time)
            )
        self.update()

    def set_display_window(self, start_time: float, end_time: float) -> None:
        """Render an externally selected piano-roll display window.

        @author Codex - added Learn MIDI overview viewport control.
        """

        if self._song is None:
            self._display_window = PracticeRegion(0.0, 0.0)
        else:
            self._display_window = self._clamp_window(PracticeRegion(start_time, end_time))
        self.update()

    def paintEvent(self, event: object) -> None:
        """Paint the full MIDI duration and the visible piano-roll window.

        @author Codex - added Learn MIDI overview viewport control.
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
            painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, "Load a MIDI song to navigate the chart.")
            painter.end()
            return

        self._paint_note_overview(painter, bar_rect)
        start_x = self._time_to_x(self._display_window.start_time)
        end_x = self._time_to_x(self._display_window.end_time)
        selected = QRectF(start_x, bar_rect.top(), max(1.0, end_x - start_x), bar_rect.height())
        painter.fillRect(selected, QColor(33, 212, 253, 42))
        painter.setPen(QPen(QColor("#21d4fd"), 2))
        painter.drawRoundedRect(selected, 4, 4)

        painter.setBrush(QColor("#21d4fd"))
        painter.setPen(QPen(QColor("#05070a"), 1))
        for x in (start_x, end_x):
            painter.drawRoundedRect(QRectF(x - 5, bar_rect.top() - 7, 10, bar_rect.height() + 14), 3, 3)

        painter.setPen(QColor("#91a4bd"))
        painter.drawText(QPoint(int(bar_rect.left()), int(bar_rect.top() - 5)), "MIDI overview")
        painter.drawText(QPoint(int(bar_rect.left()), int(bar_rect.bottom() + 16)), f"{self._song.start_time:.1f}s")
        painter.drawText(QPoint(int(bar_rect.right() - 44), int(bar_rect.bottom() + 16)), f"{self._song.end_time:.1f}s")
        painter.end()

    def mousePressEvent(self, event: object) -> None:
        """Start dragging a visible-window handle or the window body.

        @author Codex - added Learn MIDI overview viewport control.
        @author Codex - prevented overview background clicks from stealing a handle drag.
        @author Codex - added Learn overview body panning.
        """

        if self._song is None:
            return
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        start_x = self._time_to_x(self._display_window.start_time)
        end_x = self._time_to_x(self._display_window.end_time)
        self._drag_start_x = position.x()
        self._drag_start_window = self._display_window
        if self._overview_handle_hit(position, start_x):
            self._dragging = "start"
            return
        if self._overview_handle_hit(position, end_x):
            self._dragging = "end"
            return
        if self._overview_body_hit(position, start_x, end_x):
            self._dragging = "body"
            return
        self._dragging = None

    def mouseMoveEvent(self, event: object) -> None:
        """Move the active visible-window handle or body.

        @author Codex - added Learn MIDI overview viewport control.
        @author Codex - added Learn overview body panning.
        """

        if self._dragging is None or self._song is None:
            return
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self._dragging == "body":
            start_mouse_time = self._x_to_time(self._drag_start_x)
            current_mouse_time = self._x_to_time(position.x())
            delta = current_mouse_time - start_mouse_time
            duration = self._drag_start_window.end_time - self._drag_start_window.start_time
            start_time = self._drag_start_window.start_time + delta
            end_time = self._drag_start_window.end_time + delta
            if start_time < self._song.start_time:
                start_time = self._song.start_time
                end_time = start_time + duration
            if end_time > self._song.end_time:
                end_time = self._song.end_time
                start_time = end_time - duration
            window = PracticeRegion(start_time, end_time)
        else:
            handle_time = self._x_to_time(position.x())
            if self._dragging == "start":
                window = PracticeRegion(handle_time, self._display_window.end_time)
            else:
                window = PracticeRegion(self._display_window.start_time, handle_time)
        self._display_window = self._clamp_window(window)
        self.display_window_changed.emit(self._display_window.start_time, self._display_window.end_time)
        self.update()

    def mouseReleaseEvent(self, event: object) -> None:
        """Stop dragging the visible-window handle.

        @author Codex - added Learn MIDI overview viewport control.
        """

        self._dragging = None

    def _bar_rect(self) -> QRectF:
        """Return the drawable overview rectangle.

        @author Codex - added Learn MIDI overview viewport control.
        """

        return QRectF(self.rect()).adjusted(12, 22, -12, -22)

    def _overview_handle_hit(self, position: QPoint, handle_x: float) -> bool:
        """Return whether a click is inside an overview handle.

        @author Codex - prevented overview background clicks from stealing a handle drag.
        """

        rect = self._bar_rect()
        return (
            abs(position.x() - handle_x) <= HANDLE_HIT_RADIUS
            and rect.top() - 10 <= position.y() <= rect.bottom() + 10
        )

    def _overview_body_hit(self, position: QPoint, start_x: float, end_x: float) -> bool:
        """Return whether a click is inside the movable overview window body.

        @author Codex - added Learn overview body panning.
        """

        rect = self._bar_rect()
        return (
            start_x + HANDLE_HIT_RADIUS < position.x() < end_x - HANDLE_HIT_RADIUS
            and rect.top() <= position.y() <= rect.bottom()
        )

    def _time_to_x(self, seconds: float) -> float:
        """Map full-song seconds to an overview x coordinate.

        @author Codex - added Learn MIDI overview viewport control.
        """

        if self._song is None:
            return self._bar_rect().left()
        rect = self._bar_rect()
        duration = max(self._song.end_time - self._song.start_time, 0.001)
        ratio = (seconds - self._song.start_time) / duration
        return rect.left() + max(0.0, min(1.0, ratio)) * rect.width()

    def _x_to_time(self, x: float) -> float:
        """Map an overview x coordinate back to full-song seconds.

        @author Codex - added Learn MIDI overview viewport control.
        """

        if self._song is None:
            return 0.0
        rect = self._bar_rect()
        ratio = (x - rect.left()) / max(rect.width(), 1.0)
        ratio = max(0.0, min(1.0, ratio))
        return self._song.start_time + ratio * max(self._song.end_time - self._song.start_time, 0.0)

    def _paint_note_overview(self, painter: QPainter, rect: QRectF) -> None:
        """Paint compact note density lanes for the full MIDI.

        @author Codex - added Learn MIDI overview viewport control.
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

    def _clamp_window(self, window: PracticeRegion) -> PracticeRegion:
        """Clamp the displayed window to full-song bounds.

        @author Codex - added Learn MIDI overview viewport control.
        """

        if self._song is None:
            return PracticeRegion(0.0, 0.0)
        duration = max(self._song.end_time - self._song.start_time, 0.0)
        minimum_duration = min(max(duration * 0.02, 0.05), duration) if duration else 0.0
        return window.clamp(self._song.start_time, self._song.end_time, minimum_duration=minimum_duration)


class PianoRollTimeline(QWidget):
    """Piano-roll study timeline with draggable practice-region handles.

    This widget paints MIDI note spans by pitch and time. It does not choose
    the target track or advance practice; those decisions stay in the view
    composition and ``LearnController`` respectively.

    @author Codex - replaced Learn target lane with piano-roll timeline.
    """

    region_changed = Signal(float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._song: LearnSong | None = None
        self._visible_track_indexes: frozenset[int] = frozenset()
        self._target_track_index: int | None = None
        self._region = PracticeRegion(0.0, 0.0)
        self._display_window = PracticeRegion(0.0, 0.0)
        self._current_target: LearnTarget | None = None
        self._passed_indexes: frozenset[int] = frozenset()
        self._missed_indexes: frozenset[int] = frozenset()
        self._dragging: str | None = None
        self._transpose_semitones = 0

    def set_song(self, song: LearnSong | None, region: PracticeRegion | None = None) -> None:
        """Render the loaded song context on the piano roll.

        @author Codex - added Learn piano-roll song rendering.
        @author Codex - initialized Learn piano-roll display window.
        """

        self._song = song
        self._visible_track_indexes = frozenset(track.index for track in song.tracks) if song else frozenset()
        self._target_track_index = None
        if region is None and song is not None:
            region = PracticeRegion(song.start_time, song.end_time)
        self._region = region or PracticeRegion(0.0, 0.0)
        self._display_window = (
            PracticeRegion(song.start_time, song.end_time)
            if song is not None
            else PracticeRegion(0.0, 0.0)
        )
        self._current_target = None
        self._passed_indexes = frozenset()
        self._missed_indexes = frozenset()
        self.update()

    def set_display_window(self, start_time: float, end_time: float) -> None:
        """Limit the piano roll to the overview-selected visible MIDI range.

        This is a viewport concern only. It deliberately does not change the
        controller's practice region or selected Learn targets.

        @author Codex - added Learn piano-roll display window.
        """

        if self._song is None:
            self._display_window = PracticeRegion(0.0, 0.0)
        else:
            duration = max(self._song.end_time - self._song.start_time, 0.0)
            minimum_duration = min(max(duration * 0.02, 0.05), duration) if duration else 0.0
            self._display_window = PracticeRegion(start_time, end_time).clamp(
                self._song.start_time,
                self._song.end_time,
                minimum_duration=minimum_duration,
            )
        self.update()

    def set_transpose(self, semitones: int) -> None:
        """Shift the displayed target track without changing raw MIDI notes.

        The piano roll is a Learn chart view. The selected target track uses
        the same transposition as matching, while context tracks remain raw
        imported MIDI material.

        @author Codex - added Learn piano-roll transposition rendering.
        """

        self._transpose_semitones = clamp_transpose(semitones)
        self.update()

    def set_visible_tracks(self, track_indexes: frozenset[int]) -> None:
        """Apply visibility state for chart context tracks.

        @author Codex - added Learn piano-roll visibility control.
        @author Codex - removed Learn Run Mode playback controls.
        """

        self._visible_track_indexes = track_indexes
        self.update()

    def set_target_track(self, track_index: int | None) -> None:
        """Mark which track generates Learn targets.

        @author Codex - added Learn piano-roll target track highlighting.
        """

        self._target_track_index = track_index
        self.update()

    def set_state(
        self,
        *,
        region: PracticeRegion,
        current_target: LearnTarget | None,
        passed_indexes: frozenset[int],
        missed_indexes: frozenset[int],
    ) -> None:
        """Update dynamic timeline state from the controller snapshot.

        @author Codex - updated Learn timeline state for piano roll.
        @author Codex - removed playhead state from the piano-roll timeline.
        """

        self._region = region
        self._current_target = current_target
        self._passed_indexes = passed_indexes
        self._missed_indexes = missed_indexes
        self.update()

    def paintEvent(self, event: object) -> None:
        """Paint pitch lanes, MIDI notes, and practice-region handles.

        @author Codex - replaced Learn timeline rendering with piano roll.
        @author Codex - moved Learn playhead rendering into a dedicated bar.
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
        self._paint_region(painter, roll_rect)
        painter.end()

    def mousePressEvent(self, event: object) -> None:
        """Start dragging the nearest practice-region handle.

        @author Codex - updated Learn handle dragging for piano roll.
        """

        if self._song is None or self._target_track_index is None:
            return
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        start_x = self._time_to_x(self._region.start_time)
        end_x = self._time_to_x(self._region.end_time)
        if abs(position.x() - start_x) <= HANDLE_HIT_RADIUS:
            self._dragging = "start"
            return
        if abs(position.x() - end_x) <= HANDLE_HIT_RADIUS:
            self._dragging = "end"
            return
        self._dragging = "start" if abs(position.x() - start_x) < abs(position.x() - end_x) else "end"

    def mouseMoveEvent(self, event: object) -> None:
        """Move the active practice-region handle while dragging.

        @author Codex - updated Learn handle dragging for piano roll.
        """

        if self._dragging is None or self._song is None:
            return
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        handle_time = self._x_to_time(position.x())
        if self._dragging == "start":
            region = PracticeRegion(handle_time, self._region.end_time)
        else:
            region = PracticeRegion(self._region.start_time, handle_time)
        self._region = region.clamp(self._song.start_time, self._song.end_time)
        self.region_changed.emit(self._region.start_time, self._region.end_time)
        self.update()

    def mouseReleaseEvent(self, event: object) -> None:
        """Stop dragging the active practice-region handle.

        @author Codex - updated Learn handle dragging for piano roll.
        """

        self._dragging = None

    def _roll_rect(self) -> QRectF:
        """Return the drawable piano-roll rectangle.

        @author Codex - added Learn piano-roll geometry.
        """

        return QRectF(self.rect()).adjusted(58, 28, -18, -38)

    def _timeline_bounds(self) -> tuple[float, float]:
        """Return visible timeline bounds.

        @author Codex - added Learn piano-roll geometry.
        @author Codex - made Learn piano-roll bounds follow the overview viewport.
        """

        if self._song is None:
            return (0.0, 0.0)
        return (self._display_window.start_time, self._display_window.end_time)

    def _pitch_bounds(self) -> tuple[int, int]:
        """Return visible MIDI pitch bounds with a small vertical pad.

        @author Codex - added Learn piano-roll geometry.
        @author Codex - limited Learn piano-roll pitch bounds to the displayed window.
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

        @author Codex - added Learn piano-roll geometry.
        """

        rect = self._roll_rect()
        start_time, end_time = self._timeline_bounds()
        duration = max(end_time - start_time, 0.001)
        ratio = (seconds - start_time) / duration
        return rect.left() + max(0.0, min(1.0, ratio)) * rect.width()

    def _x_to_time(self, x: float) -> float:
        """Map an x coordinate back to song seconds.

        @author Codex - added Learn piano-roll geometry.
        """

        rect = self._roll_rect()
        start_time, end_time = self._timeline_bounds()
        ratio = (x - rect.left()) / max(rect.width(), 1.0)
        ratio = max(0.0, min(1.0, ratio))
        return start_time + ratio * max(end_time - start_time, 0.0)

    def _note_to_y(self, midi_note: int, rect: QRectF) -> float:
        """Map a MIDI note to the top y coordinate of its pitch lane.

        @author Codex - added Learn piano-roll geometry.
        """

        min_note, max_note = self._pitch_bounds()
        lane_count = max(1, max_note - min_note + 1)
        lane_height = rect.height() / lane_count
        return rect.top() + (max_note - midi_note) * lane_height

    def _paint_pitch_grid(self, painter: QPainter, rect: QRectF) -> None:
        """Paint horizontal pitch lanes and note labels.

        @author Codex - added Learn piano-roll pitch axis.
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

        @author Codex - added Learn piano-roll time axis.
        @author Codex - limited Learn piano-roll time grid to the displayed window.
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

        @author Codex - added Learn piano-roll note rendering.
        @author Codex - limited Learn piano-roll note rendering to the displayed window.
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

        @author Codex - added Learn piano-roll transposition rendering.
        """

        if track_index == self._target_track_index:
            return int(midi_note) + self._transpose_semitones
        return int(midi_note)

    def _paint_region(self, painter: QPainter, rect: QRectF) -> None:
        """Paint selected practice region and draggable handles.

        @author Codex - added Learn piano-roll region rendering.
        """

        start_x = self._time_to_x(self._region.start_time)
        end_x = self._time_to_x(self._region.end_time)
        selected = QRectF(start_x, rect.top(), max(1.0, end_x - start_x), rect.height())
        painter.fillRect(selected, QColor(255, 77, 77, 32))
        painter.setPen(QPen(QColor("#ff4d4d"), 3))
        painter.drawLine(int(start_x), int(rect.top()), int(start_x), int(rect.bottom()))
        painter.drawLine(int(end_x), int(rect.top()), int(end_x), int(rect.bottom()))
        painter.setBrush(QColor("#ff4d4d"))
        for x in (start_x, end_x):
            painter.drawRoundedRect(QRectF(x - 5, rect.top() - 10, 10, 20), 3, 3)

class LearnView(QWidget):
    """MIDI-driven song-practice screen.

    Learn is a study surface, so the view shows a piano-roll timeline and track
    controls. MIDI parsing, target matching, and live input
    stay behind explicit boundaries.

    @author Codex - created first Learn mode screen.
    @author Codex - replaced Learn highway-like timeline with piano roll.
    """

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._controller = LearnController()
        self._songs: list[LearnSong] = []
        self._current_song: LearnSong | None = None
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
        self.practice_view_button = QPushButton("Target")
        self.practice_view_button.setCheckable(True)
        self.practice_view_button.setChecked(True)
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
        self.expected_label = QLabel("Choose a target track to generate Learn targets.")
        self.detected_label = QLabel("Detected: --")
        self.feedback_label = QLabel(Feedback.WAITING.value)
        self.progress_label = QLabel("0 / 0 targets")
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
        dump("learn", "ready")

    def activate(self) -> None:
        """Start Learn's live detector when the screen becomes active.

        @author Codex - created Learn screen activation lifecycle.
        @author Codex - aligned Learn input lifecycle with Sandbox.
        """

        if not self._running:
            dump("learn", "activate")
            self.start_input()

    def deactivate(self) -> None:
        """Stop resources owned by Learn when leaving the screen.

        @author Codex - created Learn screen activation lifecycle.
        @author Codex - removed Learn Run Mode playback lifecycle.
        """

        self._controller.pause()
        self.stop_input()
        dump("learn", "deactivate")

    def closeEvent(self, event: object) -> None:
        """Release Learn input resources when the widget closes.

        @author Codex - created Learn screen activation lifecycle.
        """

        self.deactivate()
        super().closeEvent(event)

    def _build_layout(self) -> None:
        """Build the Learn screen layout.

        @author Codex - created first Learn mode screen.
        @author Codex - replaced Learn layout with piano roll and track panel.
        @author Codex - moved Learn readouts into the side rail to prioritize the piano roll.
        @author Codex - added Learn MIDI overview above the piano roll.
        @author Codex - added a dedicated Learn playhead bar.
        @author Codex - removed Learn Run Mode controls.
        @author Codex - added side-rail view switcher for target status versus tracks.
        @author Codex - compacted song and transpose controls in the Learn toolbar.
        @author Codex - grouped Learn transpose controls and range readout.
        @author Codex - replaced visible transpose spinbox with segmented stepper.
        @author Codex - arranged Learn transpose details as explicit note readouts.
        @author Codex - compacted Learn transpose details into one toolbar line.
        @author Codex - matched Learn input controls layout to Sandbox.
        """

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Learn")
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
        switcher.addWidget(self.practice_view_button)
        switcher.addWidget(self.tracks_view_button)
        side_layout.addLayout(switcher)

        target_panel = self._info_panel("Current Target")
        target_panel.layout().addWidget(self.current_target_label)
        target_panel.layout().addWidget(self.expected_label)

        feedback_panel = self._info_panel("Feedback")
        feedback_panel.layout().addWidget(self.feedback_label)
        feedback_panel.layout().addWidget(self.detected_label)
        feedback_panel.layout().addWidget(self.progress_label)

        practice_panel = QWidget()
        practice_layout = QVBoxLayout(practice_panel)
        practice_layout.setContentsMargins(0, 0, 0, 0)
        practice_layout.setSpacing(8)
        practice_layout.addWidget(target_panel)
        practice_layout.addWidget(feedback_panel)
        practice_layout.addStretch(1)

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
        self.side_stack.addWidget(practice_panel)
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
        self.feedback_label.setObjectName("feedback")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _info_panel(self, title: str) -> QFrame:
        """Create a titled information panel for Learn status.

        @author Codex - created first Learn mode screen.
        @author Codex - made Learn status panels compact inside the side rail.
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
        """Wire Qt controls to Learn controller actions.

        @author Codex - created first Learn mode screen.
        @author Codex - connected Learn piano-roll track controls.
        @author Codex - connected Learn MIDI overview viewport control.
        @author Codex - connected explicit Learn transpose step buttons.
        """

        self.back_button.clicked.connect(self._go_back)
        self.song_combo.currentIndexChanged.connect(self._select_song)
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.start_button.clicked.connect(self.start_input)
        self.practice_view_button.clicked.connect(self._show_practice_panel)
        self.tracks_view_button.clicked.connect(self._show_tracks_panel)
        self.transpose_spin.valueChanged.connect(self._set_transpose)
        self.transpose_down_button.clicked.connect(self._decrement_transpose)
        self.transpose_up_button.clicked.connect(self._increment_transpose)
        self.timeline_overview.display_window_changed.connect(self._set_display_window)
        self.timeline.region_changed.connect(self._set_region)

    def _decrement_transpose(self) -> None:
        """Move the Learn chart transpose down by one semitone.

        The buttons are a compact UI adapter over the same bounded transpose
        policy as the spin box; the practice chart remains selected track plus
        clamped semitone offset.

        @author Codex - added explicit Learn transpose decrement control.
        """

        self.transpose_spin.setValue(clamp_transpose(self._transpose_semitones - 1))

    def _increment_transpose(self) -> None:
        """Move the Learn chart transpose up by one semitone.

        The buttons are a compact UI adapter over the same bounded transpose
        policy as the spin box; the practice chart remains selected track plus
        clamped semitone offset.

        @author Codex - added explicit Learn transpose increment control.
        """

        self.transpose_spin.setValue(clamp_transpose(self._transpose_semitones + 1))

    def _show_practice_panel(self) -> None:
        """Show target and feedback readouts in the side rail.

        The choice is purely a workspace layout concern. It does not alter the
        selected MIDI track or Learn practice state.

        @author Codex - added side-rail view switcher for target status versus tracks.
        """

        self.side_stack.setCurrentIndex(0)
        self.practice_view_button.setChecked(True)
        self.tracks_view_button.setChecked(False)

    def _show_tracks_panel(self) -> None:
        """Show MIDI track controls in the side rail.

        Track controls are kept one click away so target feedback has enough
        space while practicing without hiding track selection entirely.

        @author Codex - added side-rail view switcher for target status versus tracks.
        """

        self.side_stack.setCurrentIndex(1)
        self.practice_view_button.setChecked(False)
        self.tracks_view_button.setChecked(True)

    def _update_input_button(self) -> None:
        """Render live input as record/stop transport symbology.

        A red record circle means start capture; a square means stop. Using a
        play triangle here would suggest MIDI playback, while this control owns
        the microphone/input stream.

        @author Codex - replaced Learn input text with standard capture symbols.
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
        """Reload available input devices for Learn's live detector.

        This mirrors Sandbox's working input boundary. Learn does not auto-open
        a hidden stream from its constructor; activation owns that resource.

        @author Codex - aligned Learn input device selection with Sandbox.
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
            "learn",
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

        @author Codex - aligned Learn input start behavior with Sandbox.
        """

        if self._running:
            dump("learn", "input_toggle_stop")
            self.stop_input()
            return
        device_index = self.device_combo.currentData()
        if device_index is None:
            self.status_label.setText("No input device selected.")
            dump("learn", "input_start_blocked", reason="no_device")
            return
        try:
            dump("learn", "input_start_requested", device_index=device_index)
            self._input.start(int(device_index))
        except Exception as exc:
            self.status_label.setText(f"Could not open input: {exc}")
            dump("learn", "input_start_failed", device_index=device_index, error=str(exc))
            return
        self._running = True
        self._pluck_detector.reset()
        self._update_input_button()
        self.sample_rate_label.setText(f"Sample rate: {self._input.sample_rate} Hz")
        self.status_label.setText("Listening.")
        self._frame_count = 0
        self._last_readout_at = 0.0
        self._timer.start()
        dump("learn", "input_started", device_index=device_index, sample_rate=self._input.sample_rate)

    def stop_input(self) -> None:
        """Stop live capture and leave the last Learn readout visible.

        @author Codex - aligned Learn input stop behavior with Sandbox.
        """

        self._timer.stop()
        self._input.stop()
        self._running = False
        self._update_input_button()
        self.status_label.setText("Stopped.")
        dump("learn", "input_stopped")

    def _load_songs(self) -> None:
        """Load bundled MIDI songs and the fallback demo.

        @author Codex - created Learn song loading.
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
            "learn",
            "songs_loaded",
            count=len(self._songs),
            songs=[song.title for song in self._songs],
            errors=errors,
        )

    def _select_song(self, index: int) -> None:
        """Load the song and rebuild manual track controls.

        @author Codex - created explicit Learn track-choice behavior.
        @author Codex - replaced track combo with piano-roll track panel.
        @author Codex - reset Learn MIDI overview to the full loaded song.
        @author Codex - selected an obvious guitar track by default for multi-track MIDI.
        @author Codex - reset the dedicated Learn playhead bar on song changes.
        """

        song = self.song_combo.itemData(index)
        self._current_song = song if isinstance(song, LearnSong) else None
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
            dump("learn", "song_selected", index=index, valid=False)
            return

        for track in self._current_song.tracks:
            self._track_states[track.index] = TrackUiState()
            self._add_track_row(track)
        self.track_list.addStretch(1)
        display_window = PracticeRegion(self._current_song.start_time, self._current_song.end_time)
        self.timeline_overview.set_song(self._current_song, display_window)
        self.timeline.set_song(
            self._current_song,
            display_window,
        )
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
            "learn",
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

        @author Codex - added Learn track panel lifecycle.
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

        @author Codex - added Learn track panel controls.
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

        @author Codex - added Learn track panel metadata.
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

        @author Codex - added Learn transpose metadata refresh.
        """

        if self._current_song is None:
            return
        for track in self._current_song.tracks:
            label = self._track_detail_labels.get(track.index)
            if label is not None:
                label.setText(self._track_details(track))

    def _find_track(self, track_index: int) -> MidiTrackOption | None:
        """Return the current song track by MIDI index.

        @author Codex - added Learn track lookup helper.
        """

        if self._current_song is None:
            return None
        return next((track for track in self._current_song.tracks if track.index == track_index), None)

    def _select_target_track(self, track_index: int) -> None:
        """Load one track as the only source of Learn targets.

        Other tracks remain available as visible context. The
        section passed to the controller uses song-wide bounds so region handles
        can select accompaniment context wider than the target track's notes.

        @author Codex - updated explicit Learn track-choice behavior.
        """

        track = self._find_track(track_index)
        if track is None or self._current_song is None:
            self._controller.clear_section()
            self.status_label.setText("Choose a target track to practice.")
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
            "learn",
            "target_track_selected",
            track_index=track.index,
            track_name=track.name,
            transpose=self._transpose_semitones,
            current_target=_target_dump(state.current_target),
            region={
                "start": self._controller.region.start_time,
                "end": self._controller.region.end_time,
            },
        )
        self._refresh_track_details()
        self._update_transpose_readouts()
        self._render_state(state)

    def _section_for_target_track(self, track: MidiTrackOption) -> LearnSection:
        """Return the active Learn section for selected track plus transpose.

        The source track section remains raw MIDI. The returned section is the
        Learn chart, where pitch expectations reflect the current user
        correction while song timing stays unchanged.

        @author Codex - added Learn chart transposition section builder.
        """

        if self._current_song is None:
            return transpose_section(track.section, self._transpose_semitones)
        return LearnSection(
            start_time=self._current_song.start_time,
            end_time=self._current_song.end_time,
            targets=apply_transpose(track.section.targets, self._transpose_semitones),
        )

    def _set_track_visible(self, track_index: int, visible: bool) -> None:
        """Apply timeline visibility.

        @author Codex - added Learn track visibility behavior.
        @author Codex - removed Learn Run Mode playback controls.
        """

        state = self._track_states.get(track_index)
        if state is None:
            return
        state.visible = bool(visible)
        self.timeline.set_visible_tracks(self._visible_track_indexes())
        dump("learn", "track_visible_changed", track_index=track_index, visible=visible)

    def _visible_track_indexes(self) -> frozenset[int]:
        """Return track indexes currently visible on the piano roll.

        @author Codex - added Learn track visibility behavior.
        """

        return frozenset(index for index, state in self._track_states.items() if state.visible)

    def _set_transpose(self, semitones: int) -> None:
        """Apply user semitone transposition to the Learn chart only.

        This rebuilds expected targets from the raw selected track so repeated
        changes never stack offsets onto already-transposed notes. MIDI source
        data, note timing, durations, and selected region
        are left untouched.

        @author Codex - added Learn transpose UI behavior.
        @author Codex - removed Learn Run Mode playback controls.
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
            "learn",
            "transpose_changed",
            transpose=self._transpose_semitones,
            expected=expected,
            current_target=_target_dump(state.current_target if state is not None else None),
        )
        self._refresh_track_details()
        self._update_transpose_readouts()
        self._render_state(state)

    def _set_display_window(self, start_time: float, end_time: float) -> None:
        """Apply the overview handles as the piano-roll viewport.

        This handler intentionally avoids ``LearnController``. The overview bar
        answers "what part of the MIDI am I looking at?", while ``_set_region``
        answers "what part am I practicing?".

        @author Codex - added Learn MIDI overview viewport control.
        """

        if self._current_song is None:
            return
        self.timeline_overview.set_display_window(start_time, end_time)
        self.timeline.set_display_window(start_time, end_time)
        dump("learn", "display_window_changed", start=start_time, end=end_time)

    def _set_region(self, start_time: float, end_time: float) -> None:
        """Apply a piano-roll handle change as the practice region.

        @author Codex - created Learn timeline-to-controller wiring.
        @author Codex - updated region wiring for piano roll.
        @author Codex - removed Learn Run Mode playback controls.
        """

        state = self._controller.set_region(start_time, end_time)
        dump("learn", "region_changed", start=start_time, end=end_time, state=_state_dump(state))
        self._render_state(state)

    def _update_frame(self) -> None:
        """Read the newest live input frame, matching Sandbox's flow.

        @author Codex - aligned Learn input polling with Sandbox.
        """

        frame = self._input.latest_frame()
        if frame is None:
            return
        self._render_frame(frame)

    def _render_frame(self, frame: PitchFrame) -> None:
        """Render one live detector frame into Learn practice state.

        Learn shows the live pitch estimate immediately, borrowing Sandbox's
        frame-level readout. A classified pluck still owns target matching so
        transient frame noise does not advance practice.

        @author Codex - created Learn detector integration.
        @author Codex - aligned Learn frame rendering with Sandbox.
        @author Codex - added realtime Learn detected-note readout.
        @author Codex - removed Learn Run Mode play/pause gating.
        """

        self._remember_live_frame_note(frame)
        pluck = self._pluck_detector.process_frame(frame, time.monotonic())
        if pluck is not None:
            self._remember_detected_note(pluck.midi)
            state = self._controller.snapshot()
            expected = state.current_target.midi_notes if state.current_target is not None else []
            dump(
                "learn",
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
                dump("learn", "match_result", state=_state_dump(state))
                self.status_label.setText(f"Detected {pluck.note_name}.")
                self._render_state(state)
            else:
                self.status_label.setText(f"Detected {pluck.note_name}. Choose a target track to practice.")
                self._render_state()
        else:
            self.status_label.setText("Listening.")
        self._frame_count += 1
        self._last_readout_at = time.monotonic()
        if self._last_readout_at - getattr(self, "_last_frame_dump_at", 0.0) >= 0.75:
            self._last_frame_dump_at = self._last_readout_at
            state = self._controller.snapshot()
            dump(
                "learn",
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
        """Update the Learn detected-note panel from the current FFT frame.

        This is display-only. The controller still consumes pluck events, but
        the user can see the incoming note estimate immediately like in
        Sandbox.

        @author Codex - added realtime Learn detected-note readout.
        """

        peak = self._live_peak_for_frame(frame)
        if peak is None:
            return
        self._remember_detected_note(peak.midi)
        self.detected_label.setText(self._detected_text(self._latest_detected_notes))

    def _live_peak_for_frame(self, frame: PitchFrame) -> SpectrumPeak | None:
        """Return the frame-level pitch estimate Learn should display.

        The priority mirrors Sandbox's spectrum marker: use the analyzed likely
        fundamental, then a peak tagged as fundamental, then the dominant peak.

        @author Codex - added realtime Learn detected-note readout.
        """

        if frame.likely_fundamental is not None:
            return frame.likely_fundamental
        fundamentals = [peak for peak in frame.peaks if peak.harmonic_relationship == "fundamental"]
        if fundamentals:
            return min(fundamentals, key=lambda peak: peak.frequency_hz)
        return frame.dominant_peak or (frame.peaks[0] if frame.peaks else None)

    def _remember_detected_note(self, midi_note: int) -> None:
        """Keep a live detected-note readout independent from practice state.

        The screen needs to prove that live input is reaching the detector even
        before a target track is selected.

        @author Codex - added Learn paused detection readout.
        @author Codex - removed Learn Run Mode play/pause gating.
        """

        note = int(midi_note)
        previous = tuple(existing for existing in self._latest_detected_notes if existing != note)
        self._latest_detected_notes = (previous + (note,))[-8:]

    def _render_state(self, state: object | None = None) -> None:
        """Render a controller state snapshot into Learn widgets.

        @author Codex - created Learn UI state rendering.
        @author Codex - updated Learn UI rendering for piano roll.
        @author Codex - removed Learn Run Mode HUD state.
        """

        state = state or self._controller.snapshot()
        self.timeline.set_state(
            region=self._controller.region,
            current_target=state.current_target,
            passed_indexes=state.passed_target_indexes,
            missed_indexes=state.missed_target_indexes,
        )
        if state.current_target is None:
            self.current_target_label.setText("--")
            self.expected_label.setText("Choose a target track to generate Learn targets.")
        else:
            self.current_target_label.setText(self._target_title(state.current_target))
            self.expected_label.setText(self._expected_text(state.current_target, set(state.matched_notes)))

        detected_notes = self._latest_detected_notes or state.detected_notes
        self.detected_label.setText(self._detected_text(detected_notes))
        self.progress_label.setText(
            f"{state.passed_count} / {state.selected_count} passed"
            + (f" | {state.missed_count} miss" if state.missed_count == 1 else f" | {state.missed_count} misses")
        )
        self.feedback_label.setText(state.feedback.value)
        self._set_feedback_color(state.feedback)
        self._update_transpose_readouts()

    def _expected_text(self, target: LearnTarget, matched_notes: set[int]) -> str:
        """Return checklist text for the current target.

        @author Codex - created Learn target checklist rendering.
        @author Codex - added desired target frequencies to Learn.
        """

        lines = ["Expected:"]
        for midi_note in target.midi_notes:
            marker = "[x]" if midi_note in matched_notes else "[ ]"
            lines.append(f"{marker} {self._desired_note_text(midi_note)}")
        return "\n".join(lines)

    def _target_title(self, target: LearnTarget) -> str:
        """Return the current target label with desired note frequencies.

        @author Codex - added desired target frequencies to Learn.
        """

        return " + ".join(self._desired_note_text(midi_note) for midi_note in target.midi_notes)

    def _desired_note_text(self, midi_note: int) -> str:
        """Return a desired MIDI note as note name plus equal-tempered Hz.

        @author Codex - added desired target frequencies to Learn.
        """

        return f"{midi_note_name(midi_note)} ({note_to_frequency(midi_note):.1f} Hz)"

    def _detected_text(self, detected_notes: tuple[int, ...]) -> str:
        """Return detected-note text for the status panel.

        @author Codex - created Learn detected-note rendering.
        """

        if not detected_notes:
            return "Detected: --"
        names = ", ".join(midi_note_name(note) for note in detected_notes[-8:])
        return f"Detected: {names}"

    def _update_transpose_readouts(self) -> None:
        """Refresh transpose preview and guitar-range diagnostics.

        @author Codex - added Learn transpose preview and range warnings.
        @author Codex - compacted Learn transpose preview text for the toolbar.
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

        Learn keeps the guitar-range policy in ``validate_guitar_range``. The
        Qt adapter only maps that result to a compact visual warning so the
        range section stays scannable while practicing.

        @author Codex - rendered transpose range warnings as label state.
        """

        label.setProperty("rangeState", "warning" if warning else "normal")
        label.style().unpolish(label)
        label.style().polish(label)

    def _range_text(self, note_range: tuple[int, int] | None) -> str:
        """Return a compact note range for track metadata.

        @author Codex - added Learn transpose range text.
        """

        if note_range is None:
            return ""
        low, high = note_range
        if low == high:
            return midi_note_name(low)
        return f"{midi_note_name(low)} - {midi_note_name(high)}"

    def _signed_transpose(self, semitones: int) -> str:
        """Return a transpose value with an explicit plus sign when needed.

        @author Codex - added Learn transpose display formatting.
        """

        value = int(semitones)
        return f"+{value}" if value > 0 else str(value)

    def _set_feedback_color(self, feedback: Feedback) -> None:
        """Style the feedback readout for the active state.

        @author Codex - created Learn feedback rendering.
        """

        color = {
            Feedback.WAITING: "#ffd43b",
            Feedback.MISS: "#ff4d4d",
            Feedback.GOOD: "#3ddc84",
            Feedback.PERFECT: "#21d4fd",
        }.get(feedback, "#f5f5f5")
        self.feedback_label.setStyleSheet(f"color: {color};")

    def _go_back(self) -> None:
        """Leave Learn and release its resources.

        @author Codex - created Learn back navigation.
        """

        self.deactivate()
        self.back_requested.emit()

    def _apply_style(self) -> None:
        """Apply Learn screen styling.

        @author Codex - created first Learn mode screen.
        @author Codex - added piano-roll and track panel styling.
        @author Codex - removed Learn Run Mode controls.
        @author Codex - tightened Learn toolbar control spacing.
        @author Codex - styled Learn transpose as a compact grouped control.
        @author Codex - styled Learn transpose segmented stepper model.
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

    @author Codex - added Learn terminal debug dump.
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


def _target_dump(target: LearnTarget | None) -> dict[str, object] | None:
    """Return active target data needed to debug Learn matching.

    @author Codex - added Learn terminal debug dump.
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

    @author Codex - added Learn terminal debug dump.
    """

    return {
        "mode": getattr(state, "mode", None),
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
