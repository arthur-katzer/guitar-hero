"""MIDI-to-LearnTarget extraction.

This module converts adapter-level MIDI files into Learn domain objects. The
grouping rule lives here because MIDI event shape is an input detail, while the
controller only needs a sequence of targets to teach.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from interfaces import theme
from interfaces.learn.model import (
    LearnSection,
    LearnSong,
    LearnTarget,
    MidiMeasureMark,
    MidiNoteSpan,
    MidiTrackOption,
)


DEFAULT_GROUPING_TOLERANCE_SECONDS = 0.050
DEMO_NOTE_MIDIS = (40, 45, 50, 55, 59, 64)
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
PERCUSSION_CHANNEL = 9
TRACK_COLORS = theme.TRACK_COLORS


@dataclass(frozen=True)
class MidiNoteEvent:
    """One MIDI note-on/off pair converted to seconds.

    The parser keeps note events separate from Learn targets so grouping
    tolerance can evolve without changing raw MIDI extraction.

    @author Codex - created Learn MIDI note event model.
    """

    start_time: float
    end_time: float
    midi_note: int
    velocity: float
    channel: int | None


def midi_note_name(midi_note: int) -> str:
    """Return the scientific-pitch label for a MIDI note number.

    Learn shows expected targets as note names, while matching still uses MIDI
    numbers to avoid enharmonic spelling decisions in the first pass.

    @author Codex - created Learn MIDI note naming.
    """

    note = int(midi_note)
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def required_match_ratio_for_note_count(note_count: int) -> float:
    """Return the pass threshold for a target of ``note_count`` notes.

    The first implementation accepts partial large chords because live chord
    detection is still experimental, but keeps one- and two-note targets strict.

    @author Codex - created Learn target pass threshold policy.
    """

    if note_count >= 3:
        return 0.70
    return 1.0


def group_note_events(
    note_events: Iterable[MidiNoteEvent],
    *,
    grouping_tolerance_seconds: float = DEFAULT_GROUPING_TOLERANCE_SECONDS,
) -> list[LearnTarget]:
    """Group nearby MIDI starts into Learn targets.

    ``grouping_tolerance_seconds`` defines how close note-on events must be to
    count as the same playable gesture. The first note in a group anchors the
    tolerance so a fast arpeggio does not grow into one unbounded chord target.

    @author Codex - created Learn MIDI note grouping.
    """

    sorted_events = sorted(note_events, key=lambda event: (event.start_time, event.midi_note))
    groups: list[list[MidiNoteEvent]] = []
    current: list[MidiNoteEvent] = []
    anchor_start = 0.0

    for event in sorted_events:
        if not current:
            current = [event]
            anchor_start = event.start_time
            continue
        if event.start_time - anchor_start <= grouping_tolerance_seconds:
            current.append(event)
            continue
        groups.append(current)
        current = [event]
        anchor_start = event.start_time

    if current:
        groups.append(current)

    targets: list[LearnTarget] = []
    for group in groups:
        midi_notes = sorted(dict.fromkeys(event.midi_note for event in group))
        note_names = [midi_note_name(note) for note in midi_notes]
        start_time = min(event.start_time for event in group)
        end_time = max(event.end_time for event in group)
        if end_time <= start_time:
            end_time = start_time + 0.15
        targets.append(
            LearnTarget(
                start_time=float(start_time),
                end_time=float(end_time),
                original_midi_notes=list(midi_notes),
                transposed_midi_notes=list(midi_notes),
                note_names=note_names,
                label=" + ".join(note_names),
                required_match_ratio=required_match_ratio_for_note_count(len(midi_notes)),
            )
        )

    return _normalize_target_end_times(targets)


def section_from_targets(targets: Iterable[LearnTarget]) -> LearnSection:
    """Create a Learn section from already grouped targets.

    The demo path and MIDI parser both use this factory so controller tests see
    the same section bounds that the UI receives.

    @author Codex - created Learn section factory from targets.
    """

    target_list = sorted(targets, key=lambda target: target.start_time)
    if not target_list:
        return LearnSection(start_time=0.0, end_time=0.0, targets=[])
    start_time = min(target.start_time for target in target_list)
    end_time = max(target.end_time for target in target_list)
    return LearnSection(start_time=start_time, end_time=end_time, targets=target_list)


def demo_song() -> LearnSong:
    """Return the built-in Learn fallback sequence.

    Learn must be usable even when MIDI parsing fails. The demo still goes
    through the real target model instead of creating a widget-only mock.

    @author Codex - created Learn fallback demo song.
    """

    events = [
        MidiNoteEvent(
            start_time=index * 0.75,
            end_time=(index * 0.75) + 0.35,
            midi_note=midi_note,
            velocity=1.0,
            channel=None,
        )
        for index, midi_note in enumerate(DEMO_NOTE_MIDIS)
    ]
    section = section_from_targets(group_note_events(events))
    notes = tuple(_note_span_from_event(event) for event in events)
    return LearnSong(
        title="Demo Open Strings",
        path=None,
        tracks=[
            MidiTrackOption(
                index=0,
                name="Demo sequence",
                channel_labels=(),
                section=section,
                notes=notes,
                color=_track_color(0),
            )
        ],
        is_demo=True,
        measure_marks=_measure_marks_for_bounds(section.start_time, section.end_time),
    )


def discover_midi_songs(project_root: Path) -> list[Path]:
    """Return bundled MIDI files that Learn can offer by default.

    Song-library MIDIs live under ``assets/songs/midi``. The legacy
    ``assets/visualizer`` lookup remains during the asset migration because the
    current menu visualizer assets predate the Learn song library boundary.

    @author Codex - created Learn bundled MIDI discovery.
    @author Codex - moved bundled MIDI discovery to the song asset library.
    """

    midi_dirs = [
        project_root / "assets" / "songs" / "midi",
        project_root / "assets" / "visualizer",
    ]
    songs: list[Path] = []
    seen: set[Path] = set()
    for asset_dir in midi_dirs:
        if not asset_dir.exists():
            continue
        for midi_path in sorted(asset_dir.glob("*.mid")):
            resolved_path = midi_path.resolve()
            if resolved_path in seen:
                continue
            songs.append(midi_path)
            seen.add(resolved_path)
    return songs


def load_midi_song(
    midi_path: Path,
    *,
    grouping_tolerance_seconds: float = DEFAULT_GROUPING_TOLERANCE_SECONDS,
    include_drums: bool = False,
) -> LearnSong:
    """Parse one MIDI file into track-level Learn sections.

    Each non-empty melodic track becomes a selectable practice part. Percussion
    channel 9 is excluded by default because Learn teaches guitar note targets.

    @author Codex - created MIDI parser for Learn mode.
    """

    try:
        import mido
    except ImportError as exc:  # pragma: no cover - dependency failure becomes UI fallback.
        raise RuntimeError("mido is required to parse MIDI files for Learn mode") from exc

    midi_file = mido.MidiFile(str(midi_path))
    tempo_map = _tempo_map(midi_file)
    measure_marks = _measure_marks(midi_file, tempo_map)
    tracks: list[MidiTrackOption] = []

    for track_index, track in enumerate(midi_file.tracks):
        track_name = _track_name(track, fallback=f"Track {track_index}")
        notes = _track_note_events(
            track,
            ticks_per_beat=midi_file.ticks_per_beat,
            tempo_map=tempo_map,
            include_drums=include_drums,
        )
        if not notes:
            continue
        targets = group_note_events(notes, grouping_tolerance_seconds=grouping_tolerance_seconds)
        if not targets:
            continue
        channels = tuple(
            str(channel + 1)
            for channel in sorted({note.channel for note in notes if note.channel is not None})
        )
        tracks.append(
            MidiTrackOption(
                index=track_index,
                name=track_name,
                channel_labels=channels,
                section=section_from_targets(targets),
                notes=tuple(_note_span_from_event(note) for note in notes),
                color=_track_color(len(tracks)),
                instrument_labels=_program_labels(track),
            )
        )

    if not tracks:
        raise ValueError(f"No playable melodic tracks found in {midi_path}")

    return LearnSong(
        title=midi_path.stem.replace("_", " "),
        path=midi_path,
        tracks=tracks,
        measure_marks=measure_marks,
    )


def _note_span_from_event(event: MidiNoteEvent) -> MidiNoteSpan:
    """Convert a parser event into a piano-roll note span.

    @author Codex - added piano-roll MIDI span extraction.
    """

    return MidiNoteSpan(
        start_time=event.start_time,
        end_time=event.end_time,
        midi_note=event.midi_note,
        velocity=event.velocity,
        channel=event.channel,
    )


def _track_color(track_index: int) -> str:
    """Return a stable display color for a MIDI track index.

    @author Codex - added deterministic Learn track colors.
    """

    return TRACK_COLORS[track_index % len(TRACK_COLORS)]


def _program_labels(track: object) -> tuple[str, ...]:
    """Return General MIDI instrument labels used by one track.

    Program changes are metadata for the user-facing track panel. They do not
    affect target generation, which stays based on actual note events.

    @author Codex - added Learn track instrument labels.
    """

    labels: list[str] = []
    for message in track:
        if message.type != "program_change":
            continue
        program = int(getattr(message, "program", -1))
        label = f"Program {program + 1}"
        if label not in labels:
            labels.append(label)
    return tuple(labels)


def _measure_marks(midi_file: object, tempo_map: list[tuple[int, int]]) -> tuple[MidiMeasureMark, ...]:
    """Return measure starts in seconds for the MIDI file.

    This deliberately uses the first discovered time signature and defers full
    meter-map rendering until Learn needs arrangement-grade notation. The
    piano roll needs stable study landmarks, not a notation editor.

    @author Codex - added Learn piano-roll measure marks.
    """

    ticks_per_measure = midi_file.ticks_per_beat * _beats_per_measure(midi_file)
    if ticks_per_measure <= 0:
        return ()
    last_tick = _last_midi_tick(midi_file)
    marks: list[MidiMeasureMark] = []
    measure_index = 1
    tick = 0
    while tick <= last_tick:
        marks.append(
            MidiMeasureMark(
                index=measure_index,
                start_time=_seconds_at_tick(tick, tempo_map, midi_file.ticks_per_beat),
                label=str(measure_index),
            )
        )
        measure_index += 1
        tick += ticks_per_measure
    return tuple(marks)


def _measure_marks_for_bounds(start_time: float, end_time: float, spacing_seconds: float = 1.5) -> tuple[MidiMeasureMark, ...]:
    """Return simple demo measure marks for non-file Learn material.

    @author Codex - added demo piano-roll measure marks.
    """

    if end_time <= start_time:
        return ()
    marks: list[MidiMeasureMark] = []
    index = 1
    current = start_time
    while current <= end_time:
        marks.append(MidiMeasureMark(index=index, start_time=current, label=str(index)))
        index += 1
        current += spacing_seconds
    return tuple(marks)


def _beats_per_measure(midi_file: object) -> int:
    """Return the numerator of the first time signature, defaulting to 4.

    @author Codex - added Learn piano-roll measure parsing.
    """

    for track in midi_file.tracks:
        for message in track:
            if message.type == "time_signature":
                return max(1, int(getattr(message, "numerator", 4)))
    return 4


def _last_midi_tick(midi_file: object) -> int:
    """Return the latest absolute tick across all MIDI tracks.

    @author Codex - added Learn piano-roll measure parsing.
    """

    last_tick = 0
    for track in midi_file.tracks:
        absolute_tick = 0
        for message in track:
            absolute_tick += int(message.time)
        last_tick = max(last_tick, absolute_tick)
    return last_tick


def _normalize_target_end_times(targets: list[LearnTarget]) -> list[LearnTarget]:
    """Keep target blocks visible without overstating their start timing.

    MIDI note-off data can be missing or extremely short. Learn matching is
    based on target starts, so this only gives the timeline a practical block
    width.

    @author Codex - created Learn target duration normalization.
    """

    normalized: list[LearnTarget] = []
    for index, target in enumerate(targets):
        next_start = targets[index + 1].start_time if index + 1 < len(targets) else None
        minimum_end = target.start_time + 0.12
        end_time = max(target.end_time, minimum_end)
        if next_start is not None:
            end_time = min(end_time, max(target.start_time + 0.08, next_start))
        normalized.append(target.with_end_time(end_time))
    return normalized


def _tempo_map(midi_file: object) -> list[tuple[int, int]]:
    """Build a global absolute-tick tempo map for a mido MIDI file.

    Tempo can live in a conductor track or inline. Sorting tempo changes by
    absolute tick makes per-track parsing deterministic for type-1 files.

    @author Codex - created Learn MIDI tempo-map parser.
    """

    changes: list[tuple[int, int]] = [(0, 500000)]
    for track in midi_file.tracks:
        absolute_tick = 0
        for message in track:
            absolute_tick += int(message.time)
            if message.type == "set_tempo":
                changes.append((absolute_tick, int(message.tempo)))
    return sorted(dict(changes).items())


def _seconds_at_tick(abs_tick: int, tempo_map: list[tuple[int, int]], ticks_per_beat: int) -> float:
    """Convert an absolute MIDI tick to seconds.

    The conversion is local to Learn extraction so controller timing never
    depends on mido objects.

    @author Codex - created Learn MIDI tick conversion.
    """

    import mido

    seconds = 0.0
    previous_tick = 0
    previous_tempo = 500000
    for map_tick, map_tempo in tempo_map:
        if map_tick >= abs_tick:
            break
        seconds += float(mido.tick2second(map_tick - previous_tick, ticks_per_beat, previous_tempo))
        previous_tick = map_tick
        previous_tempo = map_tempo
    seconds += float(mido.tick2second(abs_tick - previous_tick, ticks_per_beat, previous_tempo))
    return seconds


def _track_name(track: object, *, fallback: str) -> str:
    """Return the MIDI track name or a stable fallback label.

    @author Codex - created Learn MIDI track label extraction.
    """

    for message in track:
        if message.type == "track_name" and getattr(message, "name", ""):
            return str(message.name)
    return fallback


def _track_note_events(
    track: object,
    *,
    ticks_per_beat: int,
    tempo_map: list[tuple[int, int]],
    include_drums: bool,
) -> list[MidiNoteEvent]:
    """Extract note-on/off pairs from one MIDI track.

    The active-note map supports repeated note-ons before note-offs by queueing
    starts per channel/note pair, matching common MIDI export behavior.

    @author Codex - created Learn MIDI note event extraction.
    """

    absolute_tick = 0
    last_tick = 0
    active: dict[tuple[int | None, int], list[tuple[int, int]]] = {}
    notes: list[MidiNoteEvent] = []

    for message in track:
        absolute_tick += int(message.time)
        last_tick = max(last_tick, absolute_tick)
        if not hasattr(message, "note"):
            continue
        channel = getattr(message, "channel", None)
        if not include_drums and channel == PERCUSSION_CHANNEL:
            continue
        note = int(message.note)
        key = (channel, note)
        velocity = int(getattr(message, "velocity", 0))
        if message.type == "note_on" and velocity > 0:
            active.setdefault(key, []).append((absolute_tick, velocity))
            continue
        if message.type == "note_off" or (message.type == "note_on" and velocity == 0):
            starts = active.get(key)
            if not starts:
                continue
            start_tick, start_velocity = starts.pop(0)
            if not starts:
                active.pop(key, None)
            start_time = _seconds_at_tick(start_tick, tempo_map, ticks_per_beat)
            end_time = _seconds_at_tick(absolute_tick, tempo_map, ticks_per_beat)
            if end_time <= start_time:
                end_time = start_time + 0.10
            notes.append(
                MidiNoteEvent(
                    start_time=start_time,
                    end_time=end_time,
                    midi_note=note,
                    velocity=max(1, start_velocity) / 127.0,
                    channel=channel,
                )
            )

    fallback_end_time = _seconds_at_tick(max(last_tick, 1), tempo_map, ticks_per_beat)
    for (channel, note), starts in active.items():
        for start_tick, start_velocity in starts:
            start_time = _seconds_at_tick(start_tick, tempo_map, ticks_per_beat)
            notes.append(
                MidiNoteEvent(
                    start_time=start_time,
                    end_time=max(start_time + 0.10, fallback_end_time),
                    midi_note=note,
                    velocity=max(1, start_velocity) / 127.0,
                    channel=channel,
                )
            )

    return sorted(notes, key=lambda note: (note.start_time, note.midi_note))
