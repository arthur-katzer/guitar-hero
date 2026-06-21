"""MIDI file rendering helpers for adapter-level playback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_RENDER_TEMPO = 500000


@dataclass(frozen=True)
class FilteredMidiRenderRequest:
    """Input boundary for region-filtered MIDI playback rendering.

    The renderer is an IO adapter: it prepares a concrete MIDI file that a
    player process can consume. Learn decides which tracks are audible and
    which region is active before calling this boundary.

    @author Codex - added filtered MIDI playback rendering boundary.
    """

    source_path: Path
    output_path: Path
    track_indexes: frozenset[int]
    start_time: float
    end_time: float
    speed: float = 1.0


class FilteredMidiRenderer:
    """Render a source MIDI into a temporary region/track-filtered MIDI file.

    FluidSynth plays files, not Learn state. This adapter translates the
    selected practice region and audible track set into a short MIDI file while
    keeping target generation and UI visibility independent from playback.

    @author Codex - added filtered MIDI playback renderer.
    """

    def render(self, request: FilteredMidiRenderRequest) -> Path:
        """Write and return the filtered MIDI file for ``request``.

        @author Codex - added filtered MIDI playback renderer.
        """

        try:
            import mido
        except ImportError as exc:  # pragma: no cover - dependency failure is surfaced by the caller.
            raise RuntimeError("mido is required to render filtered MIDI playback") from exc

        source = mido.MidiFile(str(request.source_path))
        tempo_map = _tempo_map(source)
        output = mido.MidiFile(type=1, ticks_per_beat=source.ticks_per_beat)
        output.tracks.append(_conductor_track(source))

        selected_indexes = set(request.track_indexes)
        for track_index, track in enumerate(source.tracks):
            if track_index not in selected_indexes:
                continue
            rendered_track = _render_track(
                track,
                tempo_map=tempo_map,
                ticks_per_beat=source.ticks_per_beat,
                start_time=request.start_time,
                end_time=request.end_time,
                speed=request.speed,
            )
            if len(rendered_track) > 0:
                output.tracks.append(rendered_track)

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        output.save(request.output_path)
        return request.output_path


def _conductor_track(source: object) -> object:
    """Return a minimal conductor track for deterministic rendered playback.

    Tempo is fixed because region speed is applied by scaling note timings.
    Copying arbitrary tempo maps after scaling would mix two timing policies.

    @author Codex - added filtered MIDI playback rendering boundary.
    """

    import mido

    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=DEFAULT_RENDER_TEMPO, time=0))
    for source_track in source.tracks:
        for message in source_track:
            if message.type == "time_signature":
                track.append(message.copy(time=0))
                return track
    return track


def _render_track(
    track: object,
    *,
    tempo_map: list[tuple[int, int]],
    ticks_per_beat: int,
    start_time: float,
    end_time: float,
    speed: float,
) -> object:
    """Render one source track into a clipped output track.

    @author Codex - added filtered MIDI playback renderer.
    """

    import mido

    output = mido.MidiTrack()
    for message in _initial_track_setup_messages(track):
        output.append(message.copy(time=0))

    events: list[tuple[int, int, object]] = []
    clipped_notes = _track_note_events(track, tempo_map=tempo_map, ticks_per_beat=ticks_per_beat)
    speed = max(0.05, float(speed))
    for note in clipped_notes:
        clipped_start = max(note.start_time, start_time)
        clipped_end = min(note.end_time, end_time)
        if clipped_end <= clipped_start:
            continue
        start_tick = _output_tick(clipped_start - start_time, speed=speed, ticks_per_beat=ticks_per_beat)
        end_tick = max(
            start_tick + 1,
            _output_tick(clipped_end - start_time, speed=speed, ticks_per_beat=ticks_per_beat),
        )
        channel = 0 if note.channel is None else max(0, min(15, int(note.channel)))
        velocity = max(1, min(127, int(round(note.velocity * 127))))
        events.append((start_tick, 1, mido.Message("note_on", note=note.midi_note, velocity=velocity, channel=channel, time=0)))
        events.append((end_tick, 0, mido.Message("note_off", note=note.midi_note, velocity=0, channel=channel, time=0)))

    previous_tick = 0
    for absolute_tick, _order, message in sorted(events, key=lambda item: (item[0], item[1], item[2].note)):
        message.time = max(0, absolute_tick - previous_tick)
        output.append(message)
        previous_tick = absolute_tick
    return output


@dataclass(frozen=True)
class _PlaybackNote:
    start_time: float
    end_time: float
    midi_note: int
    velocity: float
    channel: int | None


def _initial_track_setup_messages(track: object) -> Iterable[object]:
    """Yield setup messages that should apply before rendered notes play.

    @author Codex - added filtered MIDI playback renderer.
    """

    for message in track:
        if message.type in {"track_name", "program_change", "control_change"}:
            yield message


def _track_note_events(track: object, *, tempo_map: list[tuple[int, int]], ticks_per_beat: int) -> list[_PlaybackNote]:
    """Extract note spans from one source MIDI track.

    @author Codex - added filtered MIDI playback renderer.
    """

    absolute_tick = 0
    last_tick = 0
    active: dict[tuple[int | None, int], list[tuple[int, int]]] = {}
    notes: list[_PlaybackNote] = []

    for message in track:
        absolute_tick += int(message.time)
        last_tick = max(last_tick, absolute_tick)
        if not hasattr(message, "note"):
            continue
        channel = getattr(message, "channel", None)
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
            notes.append(
                _PlaybackNote(
                    start_time=start_time,
                    end_time=max(start_time + 0.01, end_time),
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
                _PlaybackNote(
                    start_time=start_time,
                    end_time=max(start_time + 0.01, fallback_end_time),
                    midi_note=note,
                    velocity=max(1, start_velocity) / 127.0,
                    channel=channel,
                )
            )
    return sorted(notes, key=lambda note: (note.start_time, note.midi_note))


def _tempo_map(midi_file: object) -> list[tuple[int, int]]:
    """Build an absolute-tick tempo map for the source MIDI file.

    @author Codex - added filtered MIDI playback renderer.
    """

    changes: list[tuple[int, int]] = [(0, DEFAULT_RENDER_TEMPO)]
    for track in midi_file.tracks:
        absolute_tick = 0
        for message in track:
            absolute_tick += int(message.time)
            if message.type == "set_tempo":
                changes.append((absolute_tick, int(message.tempo)))
    return sorted(dict(changes).items())


def _seconds_at_tick(abs_tick: int, tempo_map: list[tuple[int, int]], ticks_per_beat: int) -> float:
    """Convert a source MIDI absolute tick to seconds.

    @author Codex - added filtered MIDI playback renderer.
    """

    import mido

    seconds = 0.0
    previous_tick = 0
    previous_tempo = DEFAULT_RENDER_TEMPO
    for map_tick, map_tempo in tempo_map:
        if map_tick >= abs_tick:
            break
        seconds += float(mido.tick2second(map_tick - previous_tick, ticks_per_beat, previous_tempo))
        previous_tick = map_tick
        previous_tempo = map_tempo
    seconds += float(mido.tick2second(abs_tick - previous_tick, ticks_per_beat, previous_tempo))
    return seconds


def _output_tick(seconds_from_region_start: float, *, speed: float, ticks_per_beat: int) -> int:
    """Map region-relative seconds into the rendered MIDI clock.

    @author Codex - added filtered MIDI playback renderer.
    """

    import mido

    playback_seconds = max(0.0, seconds_from_region_start) / speed
    return int(round(mido.second2tick(playback_seconds, ticks_per_beat, DEFAULT_RENDER_TEMPO)))
