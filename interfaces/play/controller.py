"""Play mode practice state machine.

The controller owns teaching behavior and deliberately knows nothing about Qt,
MIDI files, or audio devices. Adapters feed it targets and detected MIDI notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interfaces.play.model import (
    Feedback,
    PlayMode,
    PlaySection,
    PlayTarget,
    PracticeRegion,
    TargetMatchResult,
)


PERFECT_WINDOW_SECONDS = 0.075
GOOD_WINDOW_SECONDS = 0.250
RESUME_COUNT_IN_SECONDS = 3.0
MIN_SCORING_CONFIDENCE = 0.65


@dataclass
class PlayState:
    """Snapshot of current Play practice progress.

    The view consumes this value instead of reaching into controller internals,
    which keeps UI refresh code from becoming practice policy.

    @author Codex - created Play controller state snapshot.
    """

    mode: PlayMode = PlayMode.WAIT
    feedback: Feedback = Feedback.WAITING
    playhead_time: float = 0.0
    current_target: PlayTarget | None = None
    current_index: int = -1
    selected_count: int = 0
    passed_count: int = 0
    missed_count: int = 0
    is_running: bool = False
    detected_notes: tuple[int, ...] = ()
    matched_notes: tuple[int, ...] = ()
    missing_notes: tuple[int, ...] = ()
    passed_target_indexes: frozenset[int] = field(default_factory=frozenset)
    missed_target_indexes: frozenset[int] = field(default_factory=frozenset)
    count_in_remaining: float = 0.0


def match_target(
    target: PlayTarget,
    detected_midis: set[int],
    *,
    confidence: float = 1.0,
    timing_delta_seconds: float | None = None,
) -> TargetMatchResult:
    """Compare detected MIDI notes with a Play target.

    The rule is intentionally exact for single notes and threshold-based for
    larger targets. Timing and confidence only decide GOOD versus PERFECT after
    the expected notes are sufficiently present.

    @author Codex - created Play target matching policy.
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


class PlayController:
    """State machine for target-gated Play practice.

    The controller treats detected notes as events and advances only when the
    current target is matched. Timing, playback speed, count-in, and looping
    are intentionally absent because Play no longer has Run Mode.

    @author Codex - created Play practice controller.
    @author Codex - removed Play Run Mode timing policy.
    """

    def __init__(self) -> None:
        self._section = PlaySection(start_time=0.0, end_time=0.0, targets=[])
        self._region = PracticeRegion(0.0, 0.0)
        self._targets: list[PlayTarget] = []
        self._mode = PlayMode.WAIT
        self._running = False
        self._playhead_time = 0.0
        self._started_at: float | None = None
        self._start_playhead = 0.0
        self._count_in_until: float | None = None
        self._count_in_remaining = 0.0
        self._has_started = False
        self._current_index = -1
        self._feedback = Feedback.WAITING
        self._detected_notes: tuple[int, ...] = ()
        self._matched_notes: tuple[int, ...] = ()
        self._missing_notes: tuple[int, ...] = ()
        self._passed_indexes: set[int] = set()
        self._missed_indexes: set[int] = set()
        self._silence_misses = 0

    @property
    def section(self) -> PlaySection:
        """Return the active Play section.

        @author Codex - created Play practice controller.
        """

        return self._section

    @property
    def region(self) -> PracticeRegion:
        """Return the active practice region.

        @author Codex - created Play practice controller.
        """

        return self._region

    @property
    def targets(self) -> tuple[PlayTarget, ...]:
        """Return targets inside the active region.

        @author Codex - created Play practice controller.
        """

        return tuple(self._targets)

    def set_section(self, section: PlaySection, *, preserve_region: bool = False) -> PlayState:
        """Replace the practiced section and select its full duration.

        Track changes intentionally reset timing and feedback because previous
        playhead state belongs to the old song part. Transpose changes may
        preserve the existing region because they replace pitch expectations
        without changing timing or song bounds.

        @author Codex - created Play practice section loading.
        @author Codex - added region preservation for Play chart transposition.
        """

        self._section = section
        if preserve_region:
            self._region = self._region.clamp(section.start_time, section.end_time)
        else:
            self._region = PracticeRegion(section.start_time, section.end_time).clamp(section.start_time, section.end_time)
        return self.restart()

    def clear_section(self) -> PlayState:
        """Clear Play practice when no track is selected.

        @author Codex - created explicit Play no-track state.
        """

        self._section = PlaySection(start_time=0.0, end_time=0.0, targets=[])
        self._region = PracticeRegion(0.0, 0.0)
        return self.restart()

    def set_region(self, start_time: float, end_time: float) -> PlayState:
        """Update the manual practice region selected on the timeline.

        Changing handles restarts the selected slice so practice begins from
        the first target in the new region.

        @author Codex - created Play region selection behavior.
        @author Codex - removed Play Run Mode timing policy.
        """

        self._region = PracticeRegion(start_time, end_time).clamp(
            self._section.start_time,
            self._section.end_time,
        )
        return self.restart()

    def start(self, now: float) -> PlayState:
        """Start or resume timed Play practice at ``now``.

        The first start begins from the selected region start. Later resumes
        keep the paused playhead visible and wait three seconds before the song
        clock continues, giving the player time to prepare.

        @author Codex - created Play play behavior.
        @author Codex - removed Play Run Mode timing policy.
        @author Codex - added timed Play playhead with resume count-in.
        """

        if not self._targets:
            return self.snapshot()
        self._running = True
        count_in = RESUME_COUNT_IN_SECONDS
        self._count_in_until = now + count_in
        self._count_in_remaining = count_in
        self._started_at = now + count_in
        self._start_playhead = self._playhead_time
        self._has_started = True
        return self.snapshot()

    def pause(self, now: float | None = None) -> PlayState:
        """Pause practice without changing the selected region.

        @author Codex - created Play pause behavior.
        @author Codex - added timed Play playhead with resume count-in.
        """

        self._advance_playhead(now)
        self._running = False
        self._started_at = None
        self._count_in_until = None
        self._count_in_remaining = 0.0
        return self.snapshot()

    def restart(self) -> PlayState:
        """Restart the active region from its first target.

        @author Codex - created Play section restart behavior.
        @author Codex - removed Play Run Mode timing policy.
        """

        self._reset_progress_at(self._region.start_time)
        return self.snapshot()

    def seek(self, playhead_time: float) -> PlayState:
        """Move Play to a user-selected song position.

        Seeking defines a new starting point. Targets that ended before that
        point are intentionally excluded from the new run, while a sustained
        target that still contains the playhead remains hittable.

        @author Codex - added draggable Play overview start position.
        """

        clamped_time = min(
            max(float(playhead_time), self._region.start_time),
            self._region.end_time,
        )
        self._reset_progress_at(clamped_time)
        return self.snapshot()

    def update(self, now: float) -> PlayState:
        """Advance timed Play state and return the current snapshot.

        @author Codex - removed Play Run Mode timing policy.
        @author Codex - added timed Play playhead with resume count-in.
        """

        self._advance_playhead(now)
        return self.snapshot()

    def process_detected_note(self, midi_note: int, *, confidence: float = 1.0, now: float | None = None) -> PlayState:
        """Feed one detected guitar note into Play practice.

        The detector can emit only one note event today, so this method updates
        partial target matches incrementally instead of requiring a full chord
        to arrive at once.

        @author Codex - created Play detected-note handling.
        """

        if now is not None:
            self._advance_playhead(now)
        if not self._running or self._count_in_remaining > 0:
            return self.snapshot()
        if not self._targets:
            return self.snapshot()
        if confidence < MIN_SCORING_CONFIDENCE:
            return self.snapshot()

        note = int(midi_note)
        self._detected_notes = tuple(sorted(set(self._detected_notes + (note,))))
        active_index = self._active_target_index_at_playhead()
        if active_index is None:
            self._record_silence_miss()
            return self.snapshot()
        self._current_index = active_index
        return self._process_wait_note(note, confidence=confidence)

    def snapshot(self) -> PlayState:
        """Return a value snapshot of the controller's current state.

        @author Codex - created Play controller state snapshot.
        @author Codex - removed Play Run Mode timing policy.
        """

        current_target = self._targets[self._current_index] if 0 <= self._current_index < len(self._targets) else None
        missing = self._missing_notes
        if current_target is not None and not missing and self._feedback == Feedback.IDLE:
            missing = tuple(current_target.midi_notes)
        return PlayState(
            mode=self._mode,
            feedback=self._feedback,
            playhead_time=self._playhead_time,
            current_target=current_target,
            current_index=self._current_index,
            selected_count=len(self._targets),
            passed_count=len(self._passed_indexes),
            missed_count=len(self._missed_indexes) + self._silence_misses,
            is_running=self._running,
            detected_notes=self._detected_notes,
            matched_notes=self._matched_notes,
            missing_notes=missing,
            passed_target_indexes=frozenset(self._passed_indexes),
            missed_target_indexes=frozenset(self._missed_indexes),
            count_in_remaining=self._count_in_remaining,
        )

    def _process_wait_note(self, midi_note: int, *, confidence: float) -> PlayState:
        """Apply a detected note while target-gated teaching is active.

        @author Codex - created Play Wait Mode matching behavior.
        """

        target = self._targets[self._current_index]
        detected = set(self._matched_notes)
        detected.add(midi_note)
        result = match_target(target, detected, confidence=confidence)
        self._matched_notes = result.matched_notes
        self._missing_notes = result.missing_notes
        if not result.passed:
            self._feedback = Feedback.IDLE
            return self.snapshot()

        self._feedback = result.feedback
        self._passed_indexes.add(self._current_index)
        next_index = self._next_unfinished_index(self._current_index + 1)
        if next_index is None:
            self._running = False
            self._current_index = len(self._targets) - 1
            return self.snapshot()
        self._current_index = next_index
        self._matched_notes = ()
        self._missing_notes = tuple(self._targets[next_index].midi_notes)
        return self.snapshot()

    def _advance_playhead(self, now: float | None) -> None:
        """Move the Play clock while preserving pause and count-in semantics.

        @author Codex - added timed Play playhead with resume count-in.
        """

        if not self._running or now is None or self._started_at is None:
            return
        if self._count_in_until is not None and now < self._count_in_until:
            self._count_in_remaining = max(0.0, self._count_in_until - now)
            return
        self._count_in_remaining = 0.0
        elapsed = max(0.0, now - self._started_at)
        end_time = self._region.end_time if self._region.end_time else self._section.end_time
        self._playhead_time = min(self._start_playhead + elapsed, end_time)
        self._mark_missed_targets_before_playhead()
        if self._playhead_time >= end_time:
            self._running = False
            self._started_at = None
            self._count_in_until = None

    def _mark_missed_targets_before_playhead(self) -> None:
        """Mark unfinished targets as misses once their note interval expires.

        Play scores against the selected track's note intervals. Silence during
        an active sustained target remains neutral until the MIDI note is over;
        playing during gaps is handled separately as a silence miss.

        @author Codex - added timed Play miss tracking.
        @author Codex - changed Play silence scoring to respect sustained target intervals.
        """

        for index, target in enumerate(self._targets):
            if index in self._passed_indexes or index in self._missed_indexes:
                continue
            if target.end_time < self._playhead_time:
                self._missed_indexes.add(index)
        if self._current_index in self._missed_indexes:
            next_index = self._next_unfinished_index(self._current_index + 1)
            if next_index is None:
                self._feedback = Feedback.MISS
                self._running = False
                return
            self._current_index = next_index
            self._matched_notes = ()
            self._missing_notes = tuple(self._targets[next_index].midi_notes)
            self._feedback = Feedback.MISS

    def _active_target_index_at_playhead(self) -> int | None:
        """Return the unfinished target whose note interval contains playhead.

        @author Codex - changed Play silence scoring to respect sustained target intervals.
        """

        for index, target in enumerate(self._targets):
            if index in self._passed_indexes or index in self._missed_indexes:
                continue
            if target.start_time <= self._playhead_time <= target.end_time:
                return index
        return None

    def _record_silence_miss(self) -> None:
        """Count a confident pluck while the selected target track is silent.

        This miss intentionally does not consume the next target. If the user
        plays early, Play records the timing mistake but still lets the upcoming
        note be hit when its interval arrives.

        @author Codex - added Play miss counting for plucks during expected silence.
        """

        self._silence_misses += 1
        self._feedback = Feedback.MISS

    def _reset_progress_at(self, playhead_time: float) -> None:
        """Reset Play scoring with ``playhead_time`` as the new start point.

        @author Codex - added draggable Play overview start position.
        """

        section_targets = self._section.targets_in_region(self._region)
        self._targets = [
            target
            for target in section_targets
            if target.end_time >= playhead_time
        ]
        self._running = False
        self._started_at = None
        self._count_in_until = None
        self._count_in_remaining = 0.0
        self._has_started = False
        self._passed_indexes = set()
        self._missed_indexes = set()
        self._detected_notes = ()
        self._matched_notes = ()
        self._missing_notes = tuple(self._targets[0].midi_notes) if self._targets else ()
        self._feedback = Feedback.IDLE
        self._current_index = 0 if self._targets else -1
        self._playhead_time = playhead_time
        self._start_playhead = self._playhead_time
        self._silence_misses = 0

    def _next_unfinished_index(self, start_index: int) -> int | None:
        """Return the next target not passed or missed.

        @author Codex - created Play target advance lookup.
        """

        for index in range(start_index, len(self._targets)):
            if index not in self._passed_indexes and index not in self._missed_indexes:
                return index
        return None
