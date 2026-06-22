"""Semitone transposition policy for Play charts.

Play parses MIDI files as candidate chart material. This module copies parsed
targets into corrected Play expectations without modifying the source MIDI
notes, timings, durations, or scoring bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from interfaces.play.midi_targets import midi_note_name
from interfaces.play.model import PlaySection, PlayTarget


TRANSPOSE_MIN_SEMITONES = -12
TRANSPOSE_MAX_SEMITONES = 12
STANDARD_GUITAR_LOW_MIDI = 40
STANDARD_GUITAR_HIGH_MIDI = 88


@dataclass(frozen=True)
class GuitarRangeValidation:
    """Result of validating a Play chart against the project guitar range.

    The warning is based on active Play expectations, not raw MIDI notes,
    because selected track plus transpose is the chart the user is practicing.

    @author Codex - created Play guitar-range validation result.
    """

    lowest_note: int | None
    highest_note: int | None
    low_limit: int = STANDARD_GUITAR_LOW_MIDI
    high_limit: int = STANDARD_GUITAR_HIGH_MIDI

    @property
    def has_below_range_notes(self) -> bool:
        """Return whether the active chart falls below standard guitar E2.

        @author Codex - created Play guitar-range validation result.
        """

        return self.lowest_note is not None and self.lowest_note < self.low_limit

    @property
    def has_above_range_notes(self) -> bool:
        """Return whether the active chart exceeds the configured guitar top.

        @author Codex - created Play guitar-range validation result.
        """

        return self.highest_note is not None and self.highest_note > self.high_limit

    @property
    def is_valid(self) -> bool:
        """Return whether all active chart notes are inside the guitar range.

        @author Codex - created Play guitar-range validation result.
        """

        return not self.has_below_range_notes and not self.has_above_range_notes


def clamp_transpose(semitones: int) -> int:
    """Return a user-controlled transpose value inside Play's supported range.

    The UI exposes one octave down through one octave up. Keeping the clamp in
    policy code makes tests independent from the Qt spinbox.

    @author Codex - created Play transpose bounds policy.
    """

    return max(TRANSPOSE_MIN_SEMITONES, min(TRANSPOSE_MAX_SEMITONES, int(semitones)))


def transpose_midi_note(original_midi_note: int, semitones: int) -> int:
    """Return a MIDI note shifted by ``semitones``.

    This is the core chart-correction rule: Play expectations move by
    semitone offset while source MIDI note data remains unchanged.

    @author Codex - created Play semitone transposition rule.
    """

    return int(original_midi_note) + int(semitones)


def apply_transpose(targets: Iterable[PlayTarget], semitones: int) -> list[PlayTarget]:
    """Return copied Play targets with active notes shifted by semitones.

    The original targets are not mutated. Timing, durations, and match-ratio
    policy are preserved because transposition corrects pitch only.

    @author Codex - created Play target transposition policy.
    """

    transpose = clamp_transpose(semitones)
    return [_target_with_transpose(target, transpose) for target in targets]


def transpose_section(section: PlaySection, semitones: int) -> PlaySection:
    """Return a section whose targets use transposed Play expectations.

    Region and playback timing stay in seconds, so section bounds are copied
    exactly and only target pitches are replaced.

    @author Codex - created Play section transposition policy.
    """

    return PlaySection(
        start_time=section.start_time,
        end_time=section.end_time,
        targets=apply_transpose(section.targets, semitones),
    )


def note_range_for_targets(targets: Iterable[PlayTarget], *, original: bool = False) -> tuple[int, int] | None:
    """Return the lowest and highest note for raw or active Play targets.

    Raw ranges explain the imported MIDI candidate. Active ranges explain what
    Play will display and match after transpose.

    @author Codex - created Play target range policy.
    """

    notes: list[int] = []
    for target in targets:
        source = target.original_midi_notes if original else target.midi_notes
        notes.extend(int(note) for note in source)
    if not notes:
        return None
    return (min(notes), max(notes))


def validate_guitar_range(targets: Iterable[PlayTarget]) -> GuitarRangeValidation:
    """Validate active Play target notes against the project guitar range.

    The validation deliberately runs after transposition so a consistent MIDI
    offset can remove a warning without changing the parsed MIDI file.

    @author Codex - created Play guitar-range validation policy.
    """

    note_range = note_range_for_targets(targets)
    if note_range is None:
        return GuitarRangeValidation(lowest_note=None, highest_note=None)
    return GuitarRangeValidation(lowest_note=note_range[0], highest_note=note_range[1])


def _target_with_transpose(target: PlayTarget, semitones: int) -> PlayTarget:
    """Copy one target with active expected notes shifted by semitones."""

    original_notes = [int(note) for note in target.original_midi_notes]
    transposed_notes = [transpose_midi_note(note, semitones) for note in original_notes]
    note_names = [midi_note_name(note) for note in transposed_notes]
    return replace(
        target,
        original_midi_notes=original_notes,
        transposed_midi_notes=transposed_notes,
        note_names=note_names,
        label=" + ".join(note_names),
        required_match_ratio=target.required_match_ratio,
    )
