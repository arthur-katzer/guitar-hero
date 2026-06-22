"""Core Play mode data structures.

The Play domain is intentionally independent from Qt, PortAudio, and mido.
It describes Play scoring policy in terms of targets, sections, time bounds,
and feedback so adapters can change without changing scoring rules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from pathlib import Path


class Feedback(str, Enum):
    """User-facing target feedback states for Play mode.

    @author Codex - created Play mode feedback vocabulary.
    @author Codex - added neutral Play feedback for active silence.
    """

    IDLE = "---"
    MISS = "MISS"
    GOOD = "GOOD"
    PERFECT = "PERFECT"


@dataclass(frozen=True)
class PlayTarget:
    """One note group the user is expected to play.

    MIDI notes that begin close together become one target because Play scores
    musical gestures, not raw MIDI events.

    ``original_midi_notes`` preserves the parsed MIDI chart exactly as loaded.
    ``transposed_midi_notes`` is the active Play expectation after user chart
    correction. The controller intentionally reads ``midi_notes`` as a
    compatibility property so matching follows the corrected chart without
    mutating source MIDI data.

    @author Codex - created MIDI-driven Play target model.
    @author Codex - added original/transposed note separation for Play transposition.
    """

    start_time: float
    end_time: float
    original_midi_notes: list[int]
    transposed_midi_notes: list[int]
    note_names: list[str]
    label: str
    required_match_ratio: float = 1.0

    @property
    def midi_notes(self) -> list[int]:
        """Return the active expected notes consumed by Play matching.

        Play treats selected track plus transpose as the scored chart. This
        compatibility property keeps existing controller code pointed at that
        policy while raw parsed notes remain available for previews and range
        diagnostics.

        @author Codex - added Play transposed-note compatibility boundary.
        """

        return self.transposed_midi_notes

    @property
    def note_count(self) -> int:
        """Return how many distinct expected notes are in this target.

        @author Codex - created MIDI-driven Play target model.
        @author Codex - updated count to use transposed Play expectations.
        """

        return len(self.midi_notes)

    def with_end_time(self, end_time: float) -> "PlayTarget":
        """Return this target with a normalized end time.

        The target extractor may play better timing after the next target is
        known, so immutable replacement keeps grouping and duration policy
        separated.

        @author Codex - created MIDI-driven Play target model.
        """

        return replace(self, end_time=max(self.start_time, float(end_time)))


@dataclass(frozen=True)
class PlaySection:
    """Playable target sequence for one selected MIDI track.

    The section is the controller's stable input boundary. Track parsing and
    GUI selection can vary, but scoring logic consumes only this object.

    @author Codex - created MIDI-driven Play section model.
    """

    start_time: float
    end_time: float
    targets: list[PlayTarget]

    @property
    def duration(self) -> float:
        """Return section duration in seconds.

        @author Codex - created MIDI-driven Play section model.
        """

        return max(0.0, self.end_time - self.start_time)

    def targets_in_time_range(self, region: "TimeRegion") -> list[PlayTarget]:
        """Return targets whose starts fall inside the selected time region.

        Region filtering is based on target start because Play waits for
        gestures to begin inside the selected slice.

        @author Codex - created Play region target selection.
        """

        bounded = region.clamp(self.start_time, self.end_time)
        return [
            target
            for target in self.targets
            if bounded.start_time <= target.start_time <= bounded.end_time
        ]


@dataclass(frozen=True)
class TimeRegion:
    """Time range used to clamp Play song windows and scoring bounds.

    The Play UI no longer exposes manual region handles, but the controller and
    visual adapters still need a small immutable value for bounded time spans.

    @author Codex - created Play time-region model.
    """

    start_time: float
    end_time: float

    def clamp(self, section_start: float, section_end: float, minimum_duration: float = 0.05) -> "TimeRegion":
        """Return a valid region inside a section.

        ``section_start`` and ``section_end`` define the song bounds. A tiny
        minimum duration prevents the two handles from collapsing into an
        unplayable zero-width selection.

        @author Codex - created Play time-region clamping.
        """

        low = min(float(section_start), float(section_end))
        high = max(float(section_start), float(section_end))
        if math.isclose(low, high):
            return TimeRegion(low, high)

        start = min(max(float(self.start_time), low), high)
        end = min(max(float(self.end_time), low), high)
        if start > end:
            start, end = end, start
        if end - start < minimum_duration:
            if start + minimum_duration <= high:
                end = start + minimum_duration
            else:
                start = max(low, end - minimum_duration)
        return TimeRegion(start, end)


@dataclass(frozen=True)
class MidiNoteSpan:
    """One MIDI note span used by Play's piano-roll timeline.

    Play targets are grouped scoring policy. Note spans are display material,
    which lets context tracks stay visible without becoming expected user input.

    @author Codex - added piano-roll timeline note model.
    @author Codex - removed Play Run Mode playback controls.
    """

    start_time: float
    end_time: float
    midi_note: int
    velocity: float
    channel: int | None


@dataclass(frozen=True)
class MidiMeasureMark:
    """A timeline grid mark derived from the MIDI clock.

    Measure labels are adapter-derived context for navigating a song section.
    They are not scoring policy, so the controller continues to work only in
    seconds and targets.

    @author Codex - added piano-roll measure grid model.
    """

    index: int
    start_time: float
    label: str


@dataclass(frozen=True)
class MidiTrackOption:
    """A playable MIDI track candidate for Play.

    Track metadata stays separate from Qt combo boxes so tests can enforce the
    explicit-track-choice rule without depending on widgets. Timeline notes and
    display metadata live here because they describe the loaded MIDI part, not
    the Play matching policy.

    @author Codex - created Play MIDI track option model.
    @author Codex - added piano-roll track metadata.
    @author Codex - removed Play Run Mode playback controls.
    """

    index: int
    name: str
    channel_labels: tuple[str, ...]
    section: PlaySection
    notes: tuple[MidiNoteSpan, ...] = ()
    color: str = "#21d4fd"
    instrument_labels: tuple[str, ...] = ()

    @property
    def note_count(self) -> int:
        """Return the raw MIDI note count shown in the track panel.

        Older tests and hand-built demo tracks may only have targets. Falling
        back to target note counts keeps those fixtures valid while real MIDI
        tracks report the actual note spans.

        @author Codex - added piano-roll track note count.
        """

        if self.notes:
            return len(self.notes)
        return sum(target.note_count for target in self.section.targets)

    @property
    def label(self) -> str:
        """Return a compact label for the track selector.

        @author Codex - created Play MIDI track option model.
        @author Codex - updated label for piano-roll track metadata.
        """

        channels = f" ch {','.join(self.channel_labels)}" if self.channel_labels else ""
        instruments = f" | {', '.join(self.instrument_labels)}" if self.instrument_labels else ""
        return f"{self.index}: {self.name} ({self.note_count} notes, {len(self.section.targets)} targets{channels}{instruments})"


@dataclass(frozen=True)
class PlaySong:
    """A MIDI-derived song candidate shown by Play.

    The song owns track choices but does not decide which one to score when
    multiple playable tracks exist. That preserves the product decision that
    the user selects the target part manually.

    @author Codex - created Play song model.
    """

    title: str
    path: Path | None
    tracks: list[MidiTrackOption]
    is_demo: bool = False
    measure_marks: tuple[MidiMeasureMark, ...] = ()

    @property
    def requires_track_choice(self) -> bool:
        """Return whether the user must choose a track before scoring starts.

        @author Codex - created explicit Play track-choice policy.
        """

        return len(self.tracks) > 1

    @property
    def start_time(self) -> float:
        """Return the earliest timeline time across all playable tracks.

        The piano roll shows the whole loaded song context, while the
        controller still receives only one selected scoring section.

        @author Codex - added song-level piano-roll bounds.
        """

        starts = [note.start_time for track in self.tracks for note in track.notes]
        starts.extend(track.section.start_time for track in self.tracks if track.section.targets)
        return min(starts, default=0.0)

    @property
    def end_time(self) -> float:
        """Return the latest timeline time across all playable tracks.

        @author Codex - added song-level piano-roll bounds.
        """

        ends = [note.end_time for track in self.tracks for note in track.notes]
        ends.extend(track.section.end_time for track in self.tracks if track.section.targets)
        return max(ends, default=0.0)

    @property
    def pitch_range(self) -> tuple[int, int]:
        """Return the MIDI pitch range needed by the piano roll.

        @author Codex - added song-level piano-roll pitch range.
        """

        notes = [note.midi_note for track in self.tracks for note in track.notes]
        if not notes:
            notes = [note for track in self.tracks for target in track.section.targets for note in target.midi_notes]
        if not notes:
            return (40, 64)
        return (min(notes), max(notes))


@dataclass(frozen=True)
class TargetMatchResult:
    """Result of comparing detected notes to one Play target.

    Play needs both pass/fail and per-note checklist data. This value gives
    the controller and view the same source of truth.

    @author Codex - created Play target matching result model.
    """

    passed: bool
    matched_notes: tuple[int, ...]
    missing_notes: tuple[int, ...]
    ratio: float
    feedback: Feedback
