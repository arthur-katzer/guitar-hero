"""Core Learn mode data structures.

The Learn domain is intentionally independent from Qt, PortAudio, and mido.
It describes song-practice policy in terms of targets, sections, regions, and
feedback so adapters can change without changing the teaching rules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from pathlib import Path

from interfaces import theme


class Feedback(str, Enum):
    """User-facing target feedback states for Learn mode.

    @author Codex - created Learn mode feedback vocabulary.
    """

    WAITING = "WAITING"
    MISS = "MISS"
    GOOD = "GOOD"
    PERFECT = "PERFECT"


class LearnMode(str, Enum):
    """Practice policy supported by Learn.

    @author Codex - created Learn mode timing vocabulary.
    @author Codex - removed Learn Run Mode.
    """

    WAIT = "Wait Mode"


@dataclass(frozen=True)
class LearnTarget:
    """One note group the user is expected to play.

    MIDI notes that begin close together become one target because Learn is
    teaching musical gestures, not raw MIDI events. ``required_match_ratio``
    allows partial multi-note support while chord detection remains
    experimental.

    ``original_midi_notes`` preserves the parsed MIDI chart exactly as loaded.
    ``transposed_midi_notes`` is the active Learn expectation after user chart
    correction. The controller intentionally reads ``midi_notes`` as a
    compatibility property so matching follows the corrected chart without
    mutating source MIDI data.

    @author Codex - created MIDI-driven Learn target model.
    @author Codex - added original/transposed note separation for Learn transposition.
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
        """Return the active expected notes consumed by Learn matching.

        Learn treats selected track plus transpose as the practice chart. This
        compatibility property keeps existing controller code pointed at that
        policy while raw parsed notes remain available for previews and range
        diagnostics.

        @author Codex - added Learn transposed-note compatibility boundary.
        """

        return self.transposed_midi_notes

    @property
    def note_count(self) -> int:
        """Return how many distinct expected notes are in this target.

        @author Codex - created MIDI-driven Learn target model.
        @author Codex - updated count to use transposed Learn expectations.
        """

        return len(self.midi_notes)

    def with_end_time(self, end_time: float) -> "LearnTarget":
        """Return this target with a normalized end time.

        The target extractor may learn better timing after the next target is
        known, so immutable replacement keeps grouping and duration policy
        separated.

        @author Codex - created MIDI-driven Learn target model.
        """

        return replace(self, end_time=max(self.start_time, float(end_time)))


@dataclass(frozen=True)
class LearnSection:
    """Playable target sequence for one selected MIDI track.

    The section is the controller's stable input boundary. Track parsing and
    GUI selection can vary, but practice logic consumes only this object.

    @author Codex - created MIDI-driven Learn section model.
    """

    start_time: float
    end_time: float
    targets: list[LearnTarget]

    @property
    def duration(self) -> float:
        """Return section duration in seconds.

        @author Codex - created MIDI-driven Learn section model.
        """

        return max(0.0, self.end_time - self.start_time)

    def targets_in_region(self, region: "PracticeRegion") -> list[LearnTarget]:
        """Return targets whose starts fall inside the selected practice region.

        Region filtering is based on target start because Learn waits for
        gestures to begin inside the practice slice.

        @author Codex - created Learn region target selection.
        """

        bounded = region.clamp(self.start_time, self.end_time)
        return [
            target
            for target in self.targets
            if bounded.start_time <= target.start_time <= bounded.end_time
        ]


@dataclass(frozen=True)
class PracticeRegion:
    """Manual practice range selected by the user on the Learn timeline.

    The handles are the product boundary for choosing what to practice. This
    value keeps clamping rules testable outside the draggable Qt widget.

    @author Codex - created Learn practice region model.
    """

    start_time: float
    end_time: float

    def clamp(self, section_start: float, section_end: float, minimum_duration: float = 0.05) -> "PracticeRegion":
        """Return a valid region inside a section.

        ``section_start`` and ``section_end`` define the song bounds. A tiny
        minimum duration prevents the two handles from collapsing into an
        unplayable zero-width selection.

        @author Codex - created Learn practice region clamping.
        """

        low = min(float(section_start), float(section_end))
        high = max(float(section_start), float(section_end))
        if math.isclose(low, high):
            return PracticeRegion(low, high)

        start = min(max(float(self.start_time), low), high)
        end = min(max(float(self.end_time), low), high)
        if start > end:
            start, end = end, start
        if end - start < minimum_duration:
            if start + minimum_duration <= high:
                end = start + minimum_duration
            else:
                start = max(low, end - minimum_duration)
        return PracticeRegion(start, end)


@dataclass(frozen=True)
class MidiNoteSpan:
    """One MIDI note span used by Learn's piano-roll study timeline.

    Learn targets are grouped teaching policy. Note spans are display material,
    which lets context tracks stay visible without becoming expected user input.

    @author Codex - added piano-roll timeline note model.
    @author Codex - removed Learn Run Mode playback controls.
    """

    start_time: float
    end_time: float
    midi_note: int
    velocity: float
    channel: int | None


@dataclass(frozen=True)
class MidiMeasureMark:
    """A timeline grid mark derived from the MIDI clock.

    Measure labels are adapter-derived context for studying a song section.
    They are not practice policy, so the controller continues to work only in
    seconds and targets.

    @author Codex - added piano-roll measure grid model.
    """

    index: int
    start_time: float
    label: str


@dataclass(frozen=True)
class MidiTrackOption:
    """A playable MIDI track candidate for Learn.

    Track metadata stays separate from Qt combo boxes so tests can enforce the
    explicit-track-choice rule without depending on widgets. Timeline notes and
    display metadata live here because they describe the loaded MIDI part, not
    the Learn matching policy.

    @author Codex - created Learn MIDI track option model.
    @author Codex - added piano-roll track metadata.
    @author Codex - removed Learn Run Mode playback controls.
    @author Codex - moved default track display color to the shared SynthWave theme.
    """

    index: int
    name: str
    channel_labels: tuple[str, ...]
    section: LearnSection
    notes: tuple[MidiNoteSpan, ...] = ()
    color: str = theme.TRACK_COLORS[0]
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

        @author Codex - created Learn MIDI track option model.
        @author Codex - updated label for piano-roll track metadata.
        """

        channels = f" ch {','.join(self.channel_labels)}" if self.channel_labels else ""
        instruments = f" | {', '.join(self.instrument_labels)}" if self.instrument_labels else ""
        return f"{self.index}: {self.name} ({self.note_count} notes, {len(self.section.targets)} targets{channels}{instruments})"


@dataclass(frozen=True)
class LearnSong:
    """A MIDI-derived song candidate shown by Learn.

    The song owns track choices but does not decide which one to practice when
    multiple playable tracks exist. That preserves the product decision that
    the user selects the teaching part manually.

    @author Codex - created Learn song model.
    """

    title: str
    path: Path | None
    tracks: list[MidiTrackOption]
    is_demo: bool = False
    measure_marks: tuple[MidiMeasureMark, ...] = ()

    @property
    def requires_track_choice(self) -> bool:
        """Return whether the user must choose a track before practice starts.

        @author Codex - created explicit Learn track-choice policy.
        """

        return len(self.tracks) > 1

    @property
    def start_time(self) -> float:
        """Return the earliest timeline time across all playable tracks.

        The piano roll studies the whole loaded song context, while the
        controller still receives only one selected practice section.

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
    """Result of comparing detected notes to one Learn target.

    Learn needs both pass/fail and per-note checklist data. This value gives
    the controller and view the same source of truth.

    @author Codex - created Learn target matching result model.
    """

    passed: bool
    matched_notes: tuple[int, ...]
    missing_notes: tuple[int, ...]
    ratio: float
    feedback: Feedback
