"""Learn mode practice state machine.

The controller owns teaching behavior and deliberately knows nothing about Qt,
MIDI files, or audio devices. Adapters feed it targets and detected MIDI notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from interfaces.learn.model import (
    Feedback,
    LearnMode,
    LearnSection,
    LearnTarget,
    PracticeRegion,
    TargetMatchResult,
)


PERFECT_WINDOW_SECONDS = 0.075
GOOD_WINDOW_SECONDS = 0.250


@dataclass
class LearnState:
    """Snapshot of current Learn practice progress.

    The view consumes this value instead of reaching into controller internals,
    which keeps UI refresh code from becoming practice policy.

    @author Codex - created Learn controller state snapshot.
    """

    mode: LearnMode = LearnMode.WAIT
    feedback: Feedback = Feedback.WAITING
    playhead_time: float = 0.0
    current_target: LearnTarget | None = None
    current_index: int = -1
    selected_count: int = 0
    passed_count: int = 0
    missed_count: int = 0
    is_running: bool = False
    is_counting_in: bool = False
    count_in_remaining: float = 0.0
    detected_notes: tuple[int, ...] = ()
    matched_notes: tuple[int, ...] = ()
    missing_notes: tuple[int, ...] = ()
    passed_target_indexes: frozenset[int] = field(default_factory=frozenset)
    missed_target_indexes: frozenset[int] = field(default_factory=frozenset)


def match_target(
    target: LearnTarget,
    detected_midis: set[int],
    *,
    confidence: float = 1.0,
    timing_delta_seconds: float | None = None,
) -> TargetMatchResult:
    """Compare detected MIDI notes with a Learn target.

    The rule is intentionally exact for single notes and threshold-based for
    larger targets. Timing and confidence only decide GOOD versus PERFECT after
    the expected notes are sufficiently present.

    @author Codex - created Learn target matching policy.
    """

    expected = set(target.midi_notes)
    matched = tuple(sorted(expected.intersection(detected_midis)))
    missing = tuple(sorted(expected.difference(detected_midis)))
    ratio = len(matched) / max(len(expected), 1)
    passed = ratio + 1e-9 >= target.required_match_ratio
    if not passed:
        return TargetMatchResult(
            passed=False,
            matched_notes=matched,
            missing_notes=missing,
            ratio=ratio,
            feedback=Feedback.WAITING,
        )

    exact_timing = timing_delta_seconds is None or abs(timing_delta_seconds) <= PERFECT_WINDOW_SECONDS
    exact_notes = len(matched) == len(expected)
    feedback = Feedback.PERFECT if exact_notes and confidence >= 0.85 and exact_timing else Feedback.GOOD
    return TargetMatchResult(
        passed=True,
        matched_notes=matched,
        missing_notes=missing,
        ratio=ratio,
        feedback=feedback,
    )


class LearnController:
    """State machine for Wait Mode and Run Mode practice.

    The controller treats detected notes as events. Wait Mode gates progress on
    target matches, while Run Mode maps wall-clock time into the selected song
    region and marks missed targets after their hit window passes.

    @author Codex - created Learn practice controller.
    """

    def __init__(self) -> None:
        self._section = LearnSection(start_time=0.0, end_time=0.0, targets=[])
        self._region = PracticeRegion(0.0, 0.0)
        self._targets: list[LearnTarget] = []
        self._mode = LearnMode.WAIT
        self._speed = 1.0
        self._count_in_seconds = 1.5
        self._loop_enabled = False
        self._running = False
        self._counting_in = False
        self._started_at = 0.0
        self._count_in_until = 0.0
        self._paused_playhead = 0.0
        self._current_index = -1
        self._feedback = Feedback.WAITING
        self._detected_notes: tuple[int, ...] = ()
        self._matched_notes: tuple[int, ...] = ()
        self._missing_notes: tuple[int, ...] = ()
        self._passed_indexes: set[int] = set()
        self._missed_indexes: set[int] = set()

    @property
    def section(self) -> LearnSection:
        """Return the active Learn section.

        @author Codex - created Learn practice controller.
        """

        return self._section

    @property
    def region(self) -> PracticeRegion:
        """Return the active practice region.

        @author Codex - created Learn practice controller.
        """

        return self._region

    @property
    def targets(self) -> tuple[LearnTarget, ...]:
        """Return targets inside the active region.

        @author Codex - created Learn practice controller.
        """

        return tuple(self._targets)

    def set_section(self, section: LearnSection, *, preserve_region: bool = False) -> LearnState:
        """Replace the practiced section and select its full duration.

        Track changes intentionally reset timing and feedback because previous
        playhead state belongs to the old song part. Transpose changes may
        preserve the existing region because they replace pitch expectations
        without changing timing or song bounds.

        @author Codex - created Learn practice section loading.
        @author Codex - added region preservation for Learn chart transposition.
        """

        self._section = section
        if preserve_region:
            self._region = self._region.clamp(section.start_time, section.end_time)
        else:
            self._region = PracticeRegion(section.start_time, section.end_time).clamp(section.start_time, section.end_time)
        return self.restart()

    def clear_section(self) -> LearnState:
        """Clear Learn practice when no track is selected.

        @author Codex - created explicit Learn no-track state.
        """

        self._section = LearnSection(start_time=0.0, end_time=0.0, targets=[])
        self._region = PracticeRegion(0.0, 0.0)
        return self.restart()

    def set_region(self, start_time: float, end_time: float) -> LearnState:
        """Update the manual practice region selected on the timeline.

        Changing handles restarts the selected slice so both Wait and Run modes
        begin from the first target in the new region.

        @author Codex - created Learn region selection behavior.
        """

        self._region = PracticeRegion(start_time, end_time).clamp(
            self._section.start_time,
            self._section.end_time,
        )
        return self.restart()

    def set_mode(self, mode: LearnMode) -> LearnState:
        """Switch between Wait Mode and Run Mode.

        The mode switch restarts because the meaning of playhead advancement
        changes from target-gated to wall-clock driven.

        @author Codex - created Learn mode switching behavior.
        """

        self._mode = mode
        return self.restart()

    def set_speed(self, speed: float) -> LearnState:
        """Set Run Mode playback speed as a positive multiplier.

        @author Codex - created Learn run-speed policy.
        """

        self._speed = max(0.05, float(speed))
        return self.snapshot()

    def set_count_in(self, seconds: float) -> LearnState:
        """Set Run Mode count-in duration in seconds.

        @author Codex - created Learn count-in policy.
        """

        self._count_in_seconds = max(0.0, float(seconds))
        return self.snapshot()

    def set_loop_enabled(self, enabled: bool) -> LearnState:
        """Set whether Run Mode restarts at the region end.

        @author Codex - created Learn loop-region policy.
        """

        self._loop_enabled = bool(enabled)
        return self.snapshot()

    def start(self, now: float) -> LearnState:
        """Start or resume practice at ``now``.

        Wait Mode becomes ready immediately. Run Mode holds the playhead at the
        region start until the configured count-in elapses.

        @author Codex - created Learn play behavior.
        """

        if not self._targets:
            return self.snapshot()
        self._running = True
        if self._mode == LearnMode.RUN and self._count_in_seconds > 0:
            self._counting_in = True
            self._count_in_until = now + self._count_in_seconds
            self._started_at = self._count_in_until - (
                max(0.0, self._paused_playhead - self._region.start_time) / self._speed
            )
        else:
            self._counting_in = False
            self._count_in_until = now
            self._started_at = now - (
                max(0.0, self._paused_playhead - self._region.start_time) / self._speed
            )
        return self.update(now)

    def pause(self) -> LearnState:
        """Pause practice without changing the selected region.

        @author Codex - created Learn pause behavior.
        """

        self._running = False
        self._counting_in = False
        return self.snapshot()

    def restart(self) -> LearnState:
        """Restart the active region from its first target.

        @author Codex - created Learn section restart behavior.
        @author Codex - allowed Run Mode to start at region lead-in.
        """

        self._targets = self._section.targets_in_region(self._region)
        self._running = False
        self._counting_in = False
        self._passed_indexes = set()
        self._missed_indexes = set()
        self._detected_notes = ()
        self._matched_notes = ()
        self._missing_notes = tuple(self._targets[0].midi_notes) if self._targets else ()
        self._feedback = Feedback.WAITING
        self._current_index = 0 if self._targets else -1
        if self._mode == LearnMode.RUN:
            self._paused_playhead = self._region.start_time
        else:
            self._paused_playhead = self._targets[0].start_time if self._targets else self._region.start_time
        return self.snapshot()

    def update(self, now: float) -> LearnState:
        """Advance time-based Learn state.

        Wait Mode does not advance on wall clock. Run Mode updates the playhead,
        applies misses, and handles stop-or-loop at the region end.

        @author Codex - created Learn periodic update behavior.
        """

        if self._mode == LearnMode.WAIT:
            return self.snapshot()
        if not self._running:
            return self.snapshot()
        if self._counting_in:
            remaining = self._count_in_until - now
            if remaining > 0:
                return self.snapshot(count_in_remaining=remaining)
            self._counting_in = False
            self._started_at = now - (
                max(0.0, self._paused_playhead - self._region.start_time) / self._speed
            )

        elapsed = max(0.0, now - self._started_at)
        self._paused_playhead = self._region.start_time + (elapsed * self._speed)
        if self._paused_playhead >= self._region.end_time:
            if self._loop_enabled:
                self.restart()
                self.start(now)
                return self.snapshot()
            self._paused_playhead = self._region.end_time
            self._mark_missed_through(self._paused_playhead + GOOD_WINDOW_SECONDS)
            self._running = False
            return self.snapshot()

        self._mark_missed_through(self._paused_playhead - GOOD_WINDOW_SECONDS)
        self._current_index = self._first_pending_index_near_playhead()
        return self.snapshot()

    def process_detected_note(self, midi_note: int, *, confidence: float = 1.0, now: float | None = None) -> LearnState:
        """Feed one detected guitar note into Learn practice.

        The detector can emit only one note event today, so this method updates
        partial target matches incrementally instead of requiring a full chord
        to arrive at once.

        @author Codex - created Learn detected-note handling.
        """

        note = int(midi_note)
        self._detected_notes = tuple(sorted(set(self._detected_notes + (note,))))
        if not self._targets:
            return self.snapshot()
        if self._mode == LearnMode.WAIT:
            return self._process_wait_note(note, confidence=confidence)
        return self._process_run_note(note, confidence=confidence)

    def snapshot(self, *, count_in_remaining: float | None = None) -> LearnState:
        """Return a value snapshot of the controller's current state.

        @author Codex - created Learn controller state snapshot.
        """

        current_target = self._targets[self._current_index] if 0 <= self._current_index < len(self._targets) else None
        missing = self._missing_notes
        if current_target is not None and not missing and self._feedback == Feedback.WAITING:
            missing = tuple(current_target.midi_notes)
        return LearnState(
            mode=self._mode,
            feedback=self._feedback,
            playhead_time=self._paused_playhead,
            current_target=current_target,
            current_index=self._current_index,
            selected_count=len(self._targets),
            passed_count=len(self._passed_indexes),
            missed_count=len(self._missed_indexes),
            is_running=self._running,
            is_counting_in=self._counting_in,
            count_in_remaining=(
                max(0.0, count_in_remaining)
                if count_in_remaining is not None
                else max(0.0, self._count_in_until - self._started_at if self._counting_in else 0.0)
            ),
            detected_notes=self._detected_notes,
            matched_notes=self._matched_notes,
            missing_notes=missing,
            passed_target_indexes=frozenset(self._passed_indexes),
            missed_target_indexes=frozenset(self._missed_indexes),
        )

    def _process_wait_note(self, midi_note: int, *, confidence: float) -> LearnState:
        """Apply a detected note while target-gated teaching is active.

        @author Codex - created Learn Wait Mode matching behavior.
        """

        target = self._targets[self._current_index]
        detected = set(self._matched_notes)
        detected.add(midi_note)
        result = match_target(target, detected, confidence=confidence)
        self._matched_notes = result.matched_notes
        self._missing_notes = result.missing_notes
        if not result.passed:
            self._feedback = Feedback.WAITING
            return self.snapshot()

        self._feedback = result.feedback
        self._passed_indexes.add(self._current_index)
        next_index = self._next_unfinished_index(self._current_index + 1)
        if next_index is None:
            self._running = False
            self._current_index = len(self._targets) - 1
            self._paused_playhead = target.start_time
            return self.snapshot()
        self._current_index = next_index
        self._paused_playhead = self._targets[next_index].start_time
        self._matched_notes = ()
        self._missing_notes = tuple(self._targets[next_index].midi_notes)
        return self.snapshot()

    def _process_run_note(self, midi_note: int, *, confidence: float) -> LearnState:
        """Apply a detected note while wall-clock practice is active.

        @author Codex - created Learn Run Mode matching behavior.
        """

        index = self._nearest_pending_index()
        if index is None:
            return self.snapshot()
        target = self._targets[index]
        timing_delta = self._paused_playhead - target.start_time
        if abs(timing_delta) > GOOD_WINDOW_SECONDS:
            return self.snapshot()

        detected = set(self._matched_notes if index == self._current_index else ())
        detected.add(midi_note)
        result = match_target(target, detected, confidence=confidence, timing_delta_seconds=timing_delta)
        self._current_index = index
        self._matched_notes = result.matched_notes
        self._missing_notes = result.missing_notes
        if not result.passed:
            self._feedback = Feedback.WAITING
            return self.snapshot()

        self._feedback = result.feedback
        self._passed_indexes.add(index)
        self._missed_indexes.discard(index)
        next_index = self._next_unfinished_index(index + 1)
        if next_index is not None:
            self._current_index = next_index
            self._matched_notes = ()
            self._missing_notes = tuple(self._targets[next_index].midi_notes)
        return self.snapshot()

    def _mark_missed_through(self, cutoff_time: float) -> None:
        """Mark pending Run Mode targets whose hit window has passed.

        @author Codex - created Learn Run Mode miss behavior.
        """

        changed = False
        for index, target in enumerate(self._targets):
            if index in self._passed_indexes or index in self._missed_indexes:
                continue
            if target.start_time < cutoff_time:
                self._missed_indexes.add(index)
                changed = True
        if changed:
            self._feedback = Feedback.MISS

    def _nearest_pending_index(self) -> int | None:
        """Return the pending target closest to the current playhead.

        @author Codex - created Learn Run Mode target lookup.
        """

        pending = [
            (abs(target.start_time - self._paused_playhead), index)
            for index, target in enumerate(self._targets)
            if index not in self._passed_indexes and index not in self._missed_indexes
        ]
        if not pending:
            return None
        distance, index = min(pending)
        return index if distance <= GOOD_WINDOW_SECONDS else None

    def _first_pending_index_near_playhead(self) -> int:
        """Return the next pending target index for display.

        @author Codex - created Learn current-target display lookup.
        """

        for index, target in enumerate(self._targets):
            if index in self._passed_indexes or index in self._missed_indexes:
                continue
            if target.start_time >= self._paused_playhead - GOOD_WINDOW_SECONDS:
                return index
        return len(self._targets) - 1 if self._targets else -1

    def _next_unfinished_index(self, start_index: int) -> int | None:
        """Return the next target not passed or missed.

        @author Codex - created Learn target advance lookup.
        """

        for index in range(start_index, len(self._targets)):
            if index not in self._passed_indexes and index not in self._missed_indexes:
                return index
        return None
