"""Chroma-based audio/MIDI comparison helpers for the MVP.

The comparison layer works with 12 pitch-class bins instead of trying to
transcribe exact guitar notes. That makes it useful for chords and harmony even
when the source audio is noisy or contains several notes at once.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import math
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from audio.dsp import NOTE_NAMES


DEFAULT_SAMPLE_RATE = 22050
DEFAULT_HOP_LENGTH = 1024
DEFAULT_MATCH_THRESHOLD = 0.75
DEFAULT_WEAK_THRESHOLD = 0.45
DEFAULT_MAX_DTW_CELLS = 10_000_000


@dataclass(frozen=True)
class ChromaSequence:
    """A time-indexed sequence of normalized chroma vectors."""

    chroma: np.ndarray
    times: np.ndarray
    energy: np.ndarray
    frame_rate: float
    label: str = ""

    @property
    def frame_count(self) -> int:
        return int(len(self.times))

    @property
    def duration(self) -> float:
        if len(self.times) == 0:
            return 0.0
        if len(self.times) == 1:
            return float(self.times[0])
        return float(self.times[-1] + np.median(np.diff(self.times)))


@dataclass(frozen=True)
class MidiNote:
    """One MIDI note event converted to seconds."""

    start: float
    end: float
    note: int
    velocity: float
    channel: int | None = None

    @property
    def pitch_class(self) -> int:
        return int(self.note) % 12


@dataclass(frozen=True)
class ComparisonFrame:
    time_audio_sec: float
    time_midi_sec: float
    similarity: float
    status: str
    audio_pitch_classes: str
    midi_pitch_classes: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ChromaComparisonResult:
    alignment: str
    rows: list[ComparisonFrame]
    audio_chroma: np.ndarray
    midi_chroma: np.ndarray
    mean_similarity: float

    @property
    def similarity_percent(self) -> float:
        return self.mean_similarity * 100.0


@dataclass(frozen=True)
class TimelineSegment:
    start_audio_sec: float
    end_audio_sec: float
    start_midi_sec: float
    end_midi_sec: float
    status: str
    mean_similarity: float
    min_similarity: float
    max_similarity: float
    audio_pitch_classes: str
    midi_pitch_classes: str

    def to_text(self) -> str:
        return (
            f"{self.start_audio_sec:.2f}s-{self.end_audio_sec:.2f}s audio "
            f"({self.start_midi_sec:.2f}s-{self.end_midi_sec:.2f}s MIDI): "
            f"{self.status.replace('_', ' ')} "
            f"mean={self.mean_similarity:.3f} "
            f"range={self.min_similarity:.3f}-{self.max_similarity:.3f} "
            f"audio=[{self.audio_pitch_classes or '-'}] "
            f"midi=[{self.midi_pitch_classes or '-'}]"
        )


def load_audio(path: str | Path, sample_rate: int = DEFAULT_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Load an audio file as mono float samples."""

    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        import librosa
    except ImportError:
        from audio.io import load_audio as load_audio_fallback

        return load_audio_fallback(audio_path, sample_rate=sample_rate)

    samples, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    return np.nan_to_num(samples.astype(np.float32), copy=False), int(sr)


def extract_audio_chroma(
    audio: np.ndarray | Sequence[float],
    sample_rate: int,
    *,
    hop_length: int = DEFAULT_HOP_LENGTH,
    method: str = "cqt",
    silence_threshold: float = 0.001,
) -> ChromaSequence:
    """Extract a normalized chroma timeline from audio samples."""

    try:
        import librosa
    except ImportError:
        return _extract_audio_chroma_numpy(
            audio,
            sample_rate,
            hop_length=hop_length,
            silence_threshold=silence_threshold,
        )

    mono = _to_mono_float(audio)
    if len(mono) == 0 or sample_rate <= 0:
        return _empty_sequence(label="audio")

    method = method.lower()
    if method not in {"cqt", "stft"}:
        raise ValueError("method must be 'cqt' or 'stft'")

    if method == "cqt":
        try:
            chroma = librosa.feature.chroma_cqt(
                y=mono,
                sr=sample_rate,
                hop_length=hop_length,
            )
        except Exception:
            chroma = librosa.feature.chroma_stft(
                y=mono,
                sr=sample_rate,
                hop_length=hop_length,
                n_fft=4096,
            )
    else:
        chroma = librosa.feature.chroma_stft(
            y=mono,
            sr=sample_rate,
            hop_length=hop_length,
            n_fft=4096,
        )

    frames = np.nan_to_num(chroma.T.astype(np.float64), copy=False)
    rms = librosa.feature.rms(y=mono, hop_length=hop_length)[0]
    energy = _fit_length(rms.astype(np.float64), len(frames))
    times = librosa.frames_to_time(np.arange(len(frames)), sr=sample_rate, hop_length=hop_length)
    normalized = _normalize_chroma_rows(frames, energy=energy, silence_threshold=silence_threshold)
    return ChromaSequence(
        chroma=normalized,
        times=times.astype(np.float64),
        energy=energy,
        frame_rate=float(sample_rate) / float(hop_length),
        label="audio",
    )


def load_midi(path: str | Path, *, include_drums: bool = False) -> list[MidiNote]:
    """Load MIDI notes and convert event times to seconds."""

    try:
        import mido
    except ImportError as exc:
        raise RuntimeError(
            "mido is required for MIDI parsing. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    midi_path = Path(path)
    if not midi_path.exists():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")

    midi_file = mido.MidiFile(str(midi_path))
    tempo = 500000
    elapsed = 0.0
    active: dict[tuple[int | None, int], list[tuple[float, int]]] = {}
    notes: list[MidiNote] = []

    for message in mido.merge_tracks(midi_file.tracks):
        elapsed += float(mido.tick2second(message.time, midi_file.ticks_per_beat, tempo))

        if message.type == "set_tempo":
            tempo = int(message.tempo)
            continue

        if not hasattr(message, "note"):
            continue

        channel = getattr(message, "channel", None)
        if not include_drums and channel == 9:
            continue

        key = (channel, int(message.note))
        if message.type == "note_on" and getattr(message, "velocity", 0) > 0:
            active.setdefault(key, []).append((elapsed, int(message.velocity)))
            continue

        if message.type == "note_off" or (
            message.type == "note_on" and getattr(message, "velocity", 0) == 0
        ):
            starts = active.get(key)
            if not starts:
                continue
            start, velocity = starts.pop(0)
            if not starts:
                active.pop(key, None)
            if elapsed > start:
                notes.append(
                    MidiNote(
                        start=float(start),
                        end=float(elapsed),
                        note=int(message.note),
                        velocity=max(1, velocity) / 127.0,
                        channel=channel,
                    )
                )

    for (channel, note), starts in active.items():
        for start, velocity in starts:
            if elapsed > start:
                notes.append(
                    MidiNote(
                        start=float(start),
                        end=float(elapsed),
                        note=int(note),
                        velocity=max(1, velocity) / 127.0,
                        channel=channel,
                    )
                )

    return sorted(notes, key=lambda note: (note.start, note.note))


def midi_to_chroma(
    path: str | Path,
    *,
    frame_rate: float | None = None,
    times: np.ndarray | Sequence[float] | None = None,
    duration: float | None = None,
    include_drums: bool = False,
) -> ChromaSequence:
    """Convert a MIDI file to a chroma timeline without audio synthesis."""

    notes = load_midi(path, include_drums=include_drums)
    return midi_notes_to_chroma(
        notes,
        frame_rate=frame_rate,
        times=times,
        duration=duration,
        label="midi",
    )


def midi_notes_to_chroma(
    notes: Iterable[MidiNote],
    *,
    frame_rate: float | None = None,
    times: np.ndarray | Sequence[float] | None = None,
    duration: float | None = None,
    label: str = "midi",
) -> ChromaSequence:
    """Convert already-loaded MIDI notes to normalized chroma frames."""

    note_list = list(notes)
    if frame_rate is None:
        frame_rate = DEFAULT_SAMPLE_RATE / DEFAULT_HOP_LENGTH

    if times is None:
        inferred_duration = max((note.end for note in note_list), default=0.0)
        if duration is not None:
            inferred_duration = max(inferred_duration, float(duration))
        frame_count = max(1, int(math.ceil(inferred_duration * frame_rate)) + 1)
        frame_times = np.arange(frame_count, dtype=np.float64) / float(frame_rate)
    else:
        frame_times = np.asarray(times, dtype=np.float64)
        frame_count = int(len(frame_times))

    if frame_count == 0:
        return _empty_sequence(label=label)

    chroma = np.zeros((frame_count, 12), dtype=np.float64)
    energy = np.zeros(frame_count, dtype=np.float64)
    step = _frame_step(frame_times, frame_rate)
    frame_starts = frame_times - (step / 2.0)
    frame_ends = frame_times + (step / 2.0)

    for note in note_list:
        if note.end <= note.start:
            continue
        start_idx = int(np.searchsorted(frame_ends, note.start, side="right"))
        end_idx = int(np.searchsorted(frame_starts, note.end, side="left"))
        start_idx = max(0, min(frame_count, start_idx))
        end_idx = max(start_idx, min(frame_count, end_idx))
        if end_idx <= start_idx:
            nearest = int(np.argmin(np.abs(frame_times - note.start)))
            start_idx = nearest
            end_idx = min(frame_count, nearest + 1)
        value = float(max(0.0, note.velocity))
        chroma[start_idx:end_idx, note.pitch_class] += value
        energy[start_idx:end_idx] += value

    normalized = _normalize_chroma_rows(chroma, energy=energy, silence_threshold=0.0)
    return ChromaSequence(
        chroma=normalized,
        times=frame_times,
        energy=energy,
        frame_rate=float(frame_rate),
        label=label,
    )


def compare_chroma(
    audio_sequence: ChromaSequence,
    midi_sequence: ChromaSequence,
    *,
    alignment: str = "fixed",
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    weak_threshold: float = DEFAULT_WEAK_THRESHOLD,
    max_dtw_cells: int = DEFAULT_MAX_DTW_CELLS,
) -> ChromaComparisonResult:
    """Compare two chroma timelines with fixed-time or DTW alignment."""

    alignment = alignment.lower()
    if alignment == "fixed":
        return _compare_fixed(
            audio_sequence,
            midi_sequence,
            match_threshold=match_threshold,
            weak_threshold=weak_threshold,
        )
    if alignment == "dtw":
        return _compare_dtw(
            audio_sequence,
            midi_sequence,
            match_threshold=match_threshold,
            weak_threshold=weak_threshold,
            max_dtw_cells=max_dtw_cells,
        )
    raise ValueError("alignment must be 'fixed' or 'dtw'")


def align_chroma_dtw(
    audio_chroma: np.ndarray,
    midi_chroma: np.ndarray,
    *,
    max_cells: int = DEFAULT_MAX_DTW_CELLS,
) -> list[tuple[int, int]]:
    """Return a DTW warping path as ``(audio_index, midi_index)`` pairs."""

    audio = np.asarray(audio_chroma, dtype=np.float64)
    midi = np.asarray(midi_chroma, dtype=np.float64)
    if audio.ndim != 2 or midi.ndim != 2 or audio.shape[1] != 12 or midi.shape[1] != 12:
        raise ValueError("audio_chroma and midi_chroma must be shaped (frames, 12)")

    n_audio, n_midi = len(audio), len(midi)
    if n_audio == 0 or n_midi == 0:
        return []
    if n_audio * n_midi > max_cells:
        raise ValueError(
            f"DTW would require {n_audio * n_midi:,} cells; "
            f"raise --dtw-max-cells or use --alignment fixed."
        )

    similarity = cosine_similarity_matrix(audio, midi).astype(np.float32)
    distance = (1.0 - similarity).astype(np.float32)
    cost = np.empty_like(distance, dtype=np.float32)
    cost[0, 0] = distance[0, 0]

    for i in range(1, n_audio):
        cost[i, 0] = distance[i, 0] + cost[i - 1, 0]
    for j in range(1, n_midi):
        cost[0, j] = distance[0, j] + cost[0, j - 1]

    for i in range(1, n_audio):
        prev_row = cost[i - 1]
        row = cost[i]
        for j in range(1, n_midi):
            row[j] = distance[i, j] + min(prev_row[j], row[j - 1], prev_row[j - 1])

    path: list[tuple[int, int]] = []
    i = n_audio - 1
    j = n_midi - 1
    path.append((i, j))
    while i > 0 or j > 0:
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            choices = (cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
            step = int(np.argmin(choices))
            if step == 0:
                i -= 1
            elif step == 1:
                j -= 1
            else:
                i -= 1
                j -= 1
        path.append((i, j))

    path.reverse()
    return path


def cosine_similarity_rows(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Cosine similarity for aligned chroma rows, with silence handling."""

    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("left and right must have the same shape")
    if a.ndim != 2 or a.shape[1] != 12:
        raise ValueError("left and right must be shaped (frames, 12)")

    a_norm = np.linalg.norm(a, axis=1)
    b_norm = np.linalg.norm(b, axis=1)
    similarity = np.zeros(len(a), dtype=np.float64)
    valid = (a_norm > 1e-12) & (b_norm > 1e-12)
    similarity[valid] = np.sum(a[valid] * b[valid], axis=1) / (a_norm[valid] * b_norm[valid])
    similarity[(a_norm <= 1e-12) & (b_norm <= 1e-12)] = 1.0
    return np.clip(similarity, 0.0, 1.0)


def cosine_similarity_matrix(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity matrix for chroma rows."""

    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    a_norm = np.linalg.norm(a, axis=1)
    b_norm = np.linalg.norm(b, axis=1)
    a_safe = a / np.maximum(a_norm[:, None], 1e-12)
    b_safe = b / np.maximum(b_norm[:, None], 1e-12)
    similarity = a_safe @ b_safe.T
    both_silent = (a_norm <= 1e-12)[:, None] & (b_norm <= 1e-12)[None, :]
    one_silent = ((a_norm <= 1e-12)[:, None] ^ (b_norm <= 1e-12)[None, :])
    similarity[both_silent] = 1.0
    similarity[one_silent] = 0.0
    return np.clip(similarity, 0.0, 1.0)


def status_for_similarity(
    similarity: float,
    *,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    weak_threshold: float = DEFAULT_WEAK_THRESHOLD,
) -> str:
    if similarity >= match_threshold:
        return "likely_match"
    if similarity >= weak_threshold:
        return "weak_match"
    return "mismatch"


def top_pitch_classes(vector: np.ndarray | Sequence[float], *, count: int = 3, minimum: float = 0.05) -> str:
    """Return the strongest pitch classes as names plus indexes."""

    values = np.asarray(vector, dtype=np.float64)
    if values.shape != (12,) or np.linalg.norm(values) <= 1e-12:
        return ""
    order = np.argsort(values)[::-1]
    names: list[str] = []
    for pitch_class in order[:count]:
        if values[pitch_class] < minimum:
            continue
        names.append(f"{NOTE_NAMES[int(pitch_class)]}({int(pitch_class)})")
    return " ".join(names)


def generate_report(result: ChromaComparisonResult) -> list[TimelineSegment]:
    """Generate human-readable timeline segments from comparison frames."""

    return generate_timeline_segments(result)


def generate_timeline_segments(result: ChromaComparisonResult) -> list[TimelineSegment]:
    """Collapse frame rows into contiguous match/weak/mismatch regions."""

    rows = result.rows
    if not rows:
        return []

    segments: list[TimelineSegment] = []
    start = 0
    while start < len(rows):
        status = rows[start].status
        end = start + 1
        while end < len(rows) and rows[end].status == status:
            end += 1
        segments.append(_make_segment(result, start, end))
        start = end
    return segments


def write_csv_report(path: str | Path, result: ChromaComparisonResult) -> None:
    """Write the frame-level comparison report to CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "time_audio_sec",
        "time_midi_sec",
        "similarity",
        "status",
        "audio_pitch_classes",
        "midi_pitch_classes",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in result.rows:
            data = row.to_dict()
            data["time_audio_sec"] = f"{row.time_audio_sec:.6f}"
            data["time_midi_sec"] = f"{row.time_midi_sec:.6f}"
            data["similarity"] = f"{row.similarity:.6f}"
            writer.writerow(data)


def plot_similarity(
    path: str | Path,
    result: ChromaComparisonResult,
    *,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    weak_threshold: float = DEFAULT_WEAK_THRESHOLD,
) -> None:
    """Save a PNG plot of similarity over audio time."""

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for plots. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    times = [row.time_audio_sec for row in result.rows]
    values = [row.similarity for row in result.rows]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, values, linewidth=1.4, color="#2f6f9f")
    ax.axhline(match_threshold, color="#2d8a4b", linestyle="--", linewidth=1.0, label="likely match")
    ax.axhline(weak_threshold, color="#b88322", linestyle="--", linewidth=1.0, label="weak match")
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Audio time (s)")
    ax.set_ylabel("Cosine similarity")
    ax.set_title(f"Chroma similarity ({result.alignment})")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _compare_fixed(
    audio_sequence: ChromaSequence,
    midi_sequence: ChromaSequence,
    *,
    match_threshold: float,
    weak_threshold: float,
) -> ChromaComparisonResult:
    midi_resampled = resample_chroma_sequence(midi_sequence, audio_sequence.times)
    similarity = cosine_similarity_rows(audio_sequence.chroma, midi_resampled.chroma)
    rows = _comparison_rows(
        "fixed",
        audio_sequence.times,
        audio_sequence.times,
        audio_sequence.chroma,
        midi_resampled.chroma,
        similarity,
        match_threshold=match_threshold,
        weak_threshold=weak_threshold,
    )
    return ChromaComparisonResult(
        alignment="fixed",
        rows=rows,
        audio_chroma=audio_sequence.chroma,
        midi_chroma=midi_resampled.chroma,
        mean_similarity=_active_mean_similarity(
            similarity,
            audio_sequence.chroma,
            midi_resampled.chroma,
        ),
    )


def _compare_dtw(
    audio_sequence: ChromaSequence,
    midi_sequence: ChromaSequence,
    *,
    match_threshold: float,
    weak_threshold: float,
    max_dtw_cells: int,
) -> ChromaComparisonResult:
    path = align_chroma_dtw(audio_sequence.chroma, midi_sequence.chroma, max_cells=max_dtw_cells)
    if not path:
        return ChromaComparisonResult("dtw", [], np.zeros((0, 12)), np.zeros((0, 12)), 0.0)

    audio_indices: list[int] = []
    midi_indices: list[int] = []
    by_audio: dict[int, list[int]] = {}
    for audio_index, midi_index in path:
        by_audio.setdefault(audio_index, []).append(midi_index)

    for audio_index in sorted(by_audio):
        audio_indices.append(audio_index)
        midi_indices.append(int(round(float(np.mean(by_audio[audio_index])))))

    audio_aligned = audio_sequence.chroma[audio_indices]
    midi_aligned = midi_sequence.chroma[midi_indices]
    audio_times = audio_sequence.times[audio_indices]
    midi_times = midi_sequence.times[midi_indices]
    similarity = cosine_similarity_rows(audio_aligned, midi_aligned)
    rows = _comparison_rows(
        "dtw",
        audio_times,
        midi_times,
        audio_aligned,
        midi_aligned,
        similarity,
        match_threshold=match_threshold,
        weak_threshold=weak_threshold,
    )
    return ChromaComparisonResult(
        alignment="dtw",
        rows=rows,
        audio_chroma=audio_aligned,
        midi_chroma=midi_aligned,
        mean_similarity=_active_mean_similarity(similarity, audio_aligned, midi_aligned),
    )


def resample_chroma_sequence(sequence: ChromaSequence, target_times: np.ndarray | Sequence[float]) -> ChromaSequence:
    """Linearly resample chroma values to a new set of frame times."""

    times = np.asarray(target_times, dtype=np.float64)
    if len(times) == 0:
        return _empty_sequence(label=sequence.label)
    if sequence.frame_count == 0:
        return ChromaSequence(
            chroma=np.zeros((len(times), 12), dtype=np.float64),
            times=times,
            energy=np.zeros(len(times), dtype=np.float64),
            frame_rate=sequence.frame_rate,
            label=sequence.label,
        )

    chroma = np.zeros((len(times), 12), dtype=np.float64)
    for pitch_class in range(12):
        chroma[:, pitch_class] = np.interp(
            times,
            sequence.times,
            sequence.chroma[:, pitch_class],
            left=0.0,
            right=0.0,
        )
    energy = np.interp(times, sequence.times, sequence.energy, left=0.0, right=0.0)
    normalized = _normalize_chroma_rows(chroma, energy=energy, silence_threshold=0.0)
    return ChromaSequence(
        chroma=normalized,
        times=times,
        energy=energy,
        frame_rate=sequence.frame_rate,
        label=sequence.label,
    )


def _comparison_rows(
    alignment: str,
    audio_times: np.ndarray,
    midi_times: np.ndarray,
    audio_chroma: np.ndarray,
    midi_chroma: np.ndarray,
    similarity: np.ndarray,
    *,
    match_threshold: float,
    weak_threshold: float,
) -> list[ComparisonFrame]:
    rows: list[ComparisonFrame] = []
    for index, score in enumerate(similarity):
        rows.append(
            ComparisonFrame(
                time_audio_sec=float(audio_times[index]),
                time_midi_sec=float(midi_times[index]),
                similarity=float(score),
                status=status_for_similarity(
                    float(score),
                    match_threshold=match_threshold,
                    weak_threshold=weak_threshold,
                ),
                audio_pitch_classes=top_pitch_classes(audio_chroma[index]),
                midi_pitch_classes=top_pitch_classes(midi_chroma[index]),
            )
        )
    return rows


def _make_segment(result: ChromaComparisonResult, start: int, end: int) -> TimelineSegment:
    rows = result.rows[start:end]
    scores = np.asarray([row.similarity for row in rows], dtype=np.float64)
    audio_times = np.asarray([row.time_audio_sec for row in rows], dtype=np.float64)
    midi_times = np.asarray([row.time_midi_sec for row in rows], dtype=np.float64)
    all_audio_times = np.asarray([row.time_audio_sec for row in result.rows], dtype=np.float64)
    all_midi_times = np.asarray([row.time_midi_sec for row in result.rows], dtype=np.float64)
    audio_step = _frame_step(audio_times, 0.0) or _frame_step(all_audio_times, 0.0)
    midi_step = _frame_step(midi_times, 0.0) or _frame_step(all_midi_times, 0.0)
    audio_mean = np.mean(result.audio_chroma[start:end], axis=0)
    midi_mean = np.mean(result.midi_chroma[start:end], axis=0)
    return TimelineSegment(
        start_audio_sec=float(audio_times[0]),
        end_audio_sec=float(audio_times[-1] + audio_step),
        start_midi_sec=float(midi_times[0]),
        end_midi_sec=float(midi_times[-1] + midi_step),
        status=rows[0].status,
        mean_similarity=float(np.mean(scores)),
        min_similarity=float(np.min(scores)),
        max_similarity=float(np.max(scores)),
        audio_pitch_classes=top_pitch_classes(audio_mean),
        midi_pitch_classes=top_pitch_classes(midi_mean),
    )


def _active_mean_similarity(similarity: np.ndarray, audio_chroma: np.ndarray, midi_chroma: np.ndarray) -> float:
    if len(similarity) == 0:
        return 0.0
    audio_active = np.linalg.norm(audio_chroma, axis=1) > 1e-12
    midi_active = np.linalg.norm(midi_chroma, axis=1) > 1e-12
    active = audio_active | midi_active
    if np.any(active):
        return float(np.mean(similarity[active]))
    return float(np.mean(similarity))


def _normalize_chroma_rows(
    chroma: np.ndarray,
    *,
    energy: np.ndarray | None,
    silence_threshold: float,
) -> np.ndarray:
    values = np.nan_to_num(np.asarray(chroma, dtype=np.float64), copy=False)
    if values.ndim != 2 or values.shape[1] != 12:
        raise ValueError("chroma must be shaped (frames, 12)")
    normalized = np.zeros_like(values, dtype=np.float64)
    norms = np.linalg.norm(values, axis=1)
    active = norms > 1e-12
    if energy is not None:
        fitted_energy = _fit_length(np.asarray(energy, dtype=np.float64), len(values))
        active &= fitted_energy >= silence_threshold
    normalized[active] = values[active] / norms[active, None]
    return normalized


def _fit_length(values: np.ndarray, length: int) -> np.ndarray:
    if len(values) == length:
        return values
    if len(values) > length:
        return values[:length]
    if len(values) == 0:
        return np.zeros(length, dtype=np.float64)
    return np.pad(values, (0, length - len(values)), mode="edge")


def _frame_step(times: np.ndarray, frame_rate: float) -> float:
    if len(times) >= 2:
        diffs = np.diff(times)
        positive = diffs[diffs > 0]
        if len(positive):
            return float(np.median(positive))
    if frame_rate > 0:
        return 1.0 / float(frame_rate)
    return 0.0


def _to_mono_float(samples: np.ndarray | Sequence[float]) -> np.ndarray:
    array = np.asarray(samples)
    if array.ndim == 2:
        array = np.mean(array, axis=1)
    return np.nan_to_num(array.astype(np.float32), copy=False)


def _extract_audio_chroma_numpy(
    audio: np.ndarray | Sequence[float],
    sample_rate: int,
    *,
    hop_length: int,
    silence_threshold: float,
) -> ChromaSequence:
    from audio.chords import chroma_vector

    mono = _to_mono_float(audio)
    if len(mono) == 0 or sample_rate <= 0:
        return _empty_sequence(label="audio")

    window_size = max(4096, hop_length * 4)
    vectors: list[np.ndarray] = []
    energy_values: list[float] = []

    for start in range(0, len(mono), hop_length):
        chunk = mono[start : start + window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        energy = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
        energy_values.append(energy)
        if energy < silence_threshold:
            vectors.append(np.zeros(12, dtype=np.float64))
        else:
            vectors.append(chroma_vector(chunk, sample_rate))

    chroma = np.vstack(vectors) if vectors else np.zeros((0, 12), dtype=np.float64)
    energy = np.asarray(energy_values, dtype=np.float64)
    times = np.arange(len(chroma), dtype=np.float64) * (float(hop_length) / float(sample_rate))
    normalized = _normalize_chroma_rows(chroma, energy=energy, silence_threshold=silence_threshold)
    return ChromaSequence(
        chroma=normalized,
        times=times,
        energy=energy,
        frame_rate=float(sample_rate) / float(hop_length),
        label="audio",
    )


def _resample_if_needed(samples: np.ndarray, sample_rate: int, target_sample_rate: int) -> tuple[np.ndarray, int]:
    mono = _to_mono_float(samples)
    if target_sample_rate <= 0 or int(sample_rate) == int(target_sample_rate):
        return mono, int(sample_rate)
    try:
        from scipy.signal import resample_poly
    except ImportError:
        return mono, int(sample_rate)

    common = math.gcd(int(sample_rate), int(target_sample_rate))
    up = int(target_sample_rate) // common
    down = int(sample_rate) // common
    resampled = resample_poly(mono, up, down).astype(np.float32)
    return np.nan_to_num(resampled, copy=False), int(target_sample_rate)


def _empty_sequence(label: str) -> ChromaSequence:
    return ChromaSequence(
        chroma=np.zeros((0, 12), dtype=np.float64),
        times=np.zeros(0, dtype=np.float64),
        energy=np.zeros(0, dtype=np.float64),
        frame_rate=0.0,
        label=label,
    )
