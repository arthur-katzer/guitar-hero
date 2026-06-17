#!/usr/bin/env python3
"""Listen for target notes and award points after a steady match."""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from audio.dsp import (
    DEFAULT_FFT_SIZE,
    DEFAULT_MAX_FREQUENCY,
    DEFAULT_MIN_FREQUENCY,
    NOTE_NAMES,
    analyze_pitch,
    midi_to_frequency,
    midi_to_note_name,
)
from audio.device_select import find_system_audio_device, parse_device


DEFAULT_NOTES = "C4,D4,E4,F4,G4,A4,B4,C5"
NOTE_PATTERN = re.compile(r"^([A-Ga-g])([#bB]?)(-?\d+)$")
FLAT_TO_SHARP = {
    "DB": "C#",
    "EB": "D#",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
}


@dataclass
class NoteState:
    target_midi: int
    correct_seconds: float = 0.0
    best_confidence: float = 0.0
    last_detected: str = "Silence"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ask for random target notes and listen until each note is held long enough."
    )
    parser.add_argument("--list-devices", action="store_true", help="List sounddevice audio devices")
    parser.add_argument("--device", help="Input device index or name")
    parser.add_argument(
        "--system-audio",
        action="store_true",
        help="Use Windows Stereo Mix/Mixagem estéreo when available",
    )
    parser.add_argument("--sample-rate", type=int, default=48000, help="Capture sample rate")
    parser.add_argument("--chunk-ms", type=float, default=200.0, help="Analysis window size")
    parser.add_argument("--hold-seconds", type=float, default=0.6, help="Required continuous match time")
    parser.add_argument("--notes", default=DEFAULT_NOTES, help="Comma/space-separated note pool")
    parser.add_argument("--first-note", help="Force the first requested note, e.g. A4")
    parser.add_argument("--tolerance", type=int, default=0, help="Allowed MIDI-note error")
    parser.add_argument("--threshold", type=float, default=0.01, help="RMS silence threshold")
    parser.add_argument("--min-confidence", type=float, default=0.45, help="Minimum detector confidence")
    parser.add_argument("--min-frequency", type=float, default=DEFAULT_MIN_FREQUENCY)
    parser.add_argument("--max-frequency", type=float, default=DEFAULT_MAX_FREQUENCY)
    parser.add_argument("--fft-size", type=int, default=DEFAULT_FFT_SIZE)
    parser.add_argument("--seed", type=int, help="Random seed for repeatable practice order")
    args = parser.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        print(
            "error: sounddevice is required. Install dependencies with "
            "`python -m pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        return 1

    if args.list_devices:
        print(sd.query_devices())
        print(f"default device: {sd.default.device}")
        return 0

    try:
        note_pool = parse_note_pool(args.notes)
        first_note = note_name_to_midi(args.first_note) if args.first_note else None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if first_note is not None and first_note not in note_pool:
        note_pool = [first_note, *note_pool]

    rng = random.Random(args.seed)
    chooser = ShuffledNoteChooser(note_pool, rng)
    try:
        device = choose_device(sd, args.device, args.system_audio)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    chunk_seconds = max(0.05, args.chunk_ms / 1000.0)
    chunk_frames = max(1, int(args.sample_rate * chunk_seconds))

    print("Live note trainer")
    print(f"  notes: {', '.join(midi_to_note_name(note) for note in note_pool)}")
    print(f"  hold time: {args.hold_seconds:.2f}s")
    print(f"  tolerance: +/-{args.tolerance} semitone(s)")
    print(f"  device: {device!r}" if device is not None else "  device: default input")
    print("Press Ctrl+C to stop.")
    print()

    score = 0
    previous_target: int | None = None
    pending_first = first_note

    try:
        while True:
            if pending_first is not None:
                target = pending_first
                pending_first = None
            else:
                target = chooser.next(previous_target)
            previous_target = target
            score += wait_for_note(
                sd,
                target,
                score,
                sample_rate=args.sample_rate,
                chunk_frames=chunk_frames,
                chunk_seconds=chunk_seconds,
                hold_seconds=args.hold_seconds,
                tolerance=args.tolerance,
                threshold=args.threshold,
                min_confidence=args.min_confidence,
                min_frequency=args.min_frequency,
                max_frequency=args.max_frequency,
                fft_size=args.fft_size,
                device=device,
            )
    except KeyboardInterrupt:
        print()
        print(f"Final score: {score}")
        return 0


def wait_for_note(
    sounddevice_module,
    target_midi: int,
    current_score: int,
    *,
    sample_rate: int,
    chunk_frames: int,
    chunk_seconds: float,
    hold_seconds: float,
    tolerance: int,
    threshold: float,
    min_confidence: float,
    min_frequency: float,
    max_frequency: float,
    fft_size: int,
    device,
) -> int:
    state = NoteState(target_midi=target_midi)
    target_name = midi_to_note_name(target_midi)
    target_hz = midi_to_frequency(target_midi)
    print(f"Play {target_name} ({target_hz:.1f} Hz). Score: {current_score}")

    while state.correct_seconds < hold_seconds:
        capture = sounddevice_module.rec(
            chunk_frames,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device,
        )
        sounddevice_module.wait()
        samples = np.asarray(capture[:, 0], dtype=np.float32)
        detection = analyze_pitch(
            samples,
            sample_rate,
            noise_threshold=threshold,
            min_frequency=min_frequency,
            max_frequency=max_frequency,
            fft_size=fft_size,
        )

        detected_name = detection.note_name
        state.last_detected = detected_name
        if note_matches(detection.midi, target_midi, tolerance) and detection.confidence >= min_confidence:
            state.correct_seconds += chunk_seconds
            state.best_confidence = max(state.best_confidence, detection.confidence)
        else:
            state.correct_seconds = 0.0

        progress = min(1.0, state.correct_seconds / max(hold_seconds, 1e-9))
        bar = progress_bar(progress)
        sys.stdout.write(
            "\r"
            f"  heard={detected_name:8s} "
            f"conf={detection.confidence:0.2f} "
            f"rms={detection.rms:0.4f} "
            f"hold={state.correct_seconds:0.2f}/{hold_seconds:0.2f}s {bar}"
        )
        sys.stdout.flush()

    sys.stdout.write("\n")
    print(f"Point! {target_name} held for {hold_seconds:.2f}s. Confidence {state.best_confidence:.2f}.")
    print()
    return 1


class ShuffledNoteChooser:
    def __init__(self, notes: list[int], rng: random.Random):
        if not notes:
            raise ValueError("note pool cannot be empty")
        self.notes = list(dict.fromkeys(notes))
        self.rng = rng
        self.remaining: list[int] = []

    def next(self, previous: int | None) -> int:
        if len(self.notes) == 1:
            return self.notes[0]

        if not self.remaining:
            self.remaining = self.notes[:]
            self.rng.shuffle(self.remaining)
            if previous is not None and self.remaining[0] == previous:
                swap_index = next(
                    (index for index, note in enumerate(self.remaining) if note != previous),
                    0,
                )
                self.remaining[0], self.remaining[swap_index] = self.remaining[swap_index], self.remaining[0]

        return self.remaining.pop(0)


def parse_note_pool(text: str) -> list[int]:
    tokens = [token for token in re.split(r"[\s,]+", text.strip()) if token]
    if not tokens:
        raise ValueError("provide at least one note, e.g. --notes A4 or --notes C4,D4,E4")
    return [note_name_to_midi(token) for token in tokens]


def note_name_to_midi(note_name: str | None) -> int:
    if not note_name:
        raise ValueError("empty note name")
    match = NOTE_PATTERN.match(note_name.strip())
    if not match:
        raise ValueError(f"invalid note name {note_name!r}; use names like A4, C#4, or Bb3")

    letter, accidental, octave_text = match.groups()
    base = letter.upper() + accidental.upper()
    if base in FLAT_TO_SHARP:
        base = FLAT_TO_SHARP[base]
    elif base.endswith("B") and len(base) == 2:
        raise ValueError(f"unsupported flat note {note_name!r}")
    elif len(base) == 1:
        pass
    elif base not in NOTE_NAMES:
        raise ValueError(f"invalid note name {note_name!r}")

    octave = int(octave_text)
    pitch_class = NOTE_NAMES.index(base)
    midi = (octave + 1) * 12 + pitch_class
    if not 0 <= midi <= 127:
        raise ValueError(f"note {note_name!r} is outside MIDI range")
    return midi


def note_matches(detected_midi: int | None, target_midi: int, tolerance: int) -> bool:
    return detected_midi is not None and abs(detected_midi - target_midi) <= tolerance


def progress_bar(progress: float, width: int = 18) -> str:
    filled = int(round(max(0.0, min(1.0, progress)) * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def choose_device(sounddevice_module, device_text: str | None, system_audio: bool):
    if device_text and system_audio:
        raise RuntimeError("use either --device or --system-audio, not both")
    if system_audio:
        device = find_system_audio_device(sounddevice_module)
        if device is None:
            raise RuntimeError(
                "could not find Stereo Mix/Mixagem estéreo. Enable Stereo Mix in Windows "
                "recording devices, or pass --device manually."
            )
        return device
    return parse_device(device_text)


if __name__ == "__main__":
    raise SystemExit(main())
