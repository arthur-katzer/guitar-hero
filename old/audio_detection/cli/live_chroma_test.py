#!/usr/bin/env python3
"""Rough live microphone/audio-interface chroma test."""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from audio.chords import detect_chord
from audio.chroma_compare import (
    DEFAULT_HOP_LENGTH,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_WEAK_THRESHOLD,
    cosine_similarity_rows,
    extract_audio_chroma,
    status_for_similarity,
    top_pitch_classes,
)
from audio.dsp import NOTE_NAMES


NOTE_TO_PC = {name.upper(): index for index, name in enumerate(NOTE_NAMES)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture short microphone windows and print live chord/chroma diagnostics."
    )
    parser.add_argument(
        "--target",
        help="Optional target pitch classes for comparison, e.g. 0,4,7 or C,E,G. "
        "Omit it for free live chord detection.",
    )
    parser.add_argument("--list-devices", action="store_true", help="List sounddevice input/output devices")
    parser.add_argument("--device", help="Input device index or name")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--seconds", type=float, default=0.75, help="Capture window length")
    parser.add_argument("--hop-length", type=int, default=DEFAULT_HOP_LENGTH)
    parser.add_argument("--chroma-method", choices=["cqt", "stft"], default="cqt")
    parser.add_argument("--silence-threshold", type=float, default=0.001)
    parser.add_argument("--match-threshold", type=float, default=DEFAULT_MATCH_THRESHOLD)
    parser.add_argument("--weak-threshold", type=float, default=DEFAULT_WEAK_THRESHOLD)
    parser.add_argument("--once", action="store_true", help="Capture one window and exit")
    args = parser.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        print(
            "error: sounddevice is required for microphone capture. "
            "Install dependencies with `python -m pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        return 1

    if args.list_devices:
        print(sd.query_devices())
        print(f"default device: {sd.default.device}")
        return 0

    device = parse_device(args.device)
    target = None
    if args.target:
        try:
            target_classes = parse_pitch_classes(args.target)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        target = pitch_class_vector(target_classes)
        target_label = top_pitch_classes(target, count=12, minimum=0.01)
        print(f"Target: {target_label}")
        print("Press Ctrl+C to stop.")
    else:
        print("Live chord/chroma detection")
        print("  target: none")
        print(f"  device: {device!r}" if device is not None else "  device: default input")
        print("Press Ctrl+C to stop.")

    try:
        while True:
            detection = capture_and_detect(
                sd,
                sample_rate=args.sample_rate,
                seconds=args.seconds,
                hop_length=args.hop_length,
                device=device,
                chroma_method=args.chroma_method,
                silence_threshold=args.silence_threshold,
            )
            if target is None:
                print_free_detection(detection)
            else:
                print_target_comparison(
                    detection,
                    target,
                    match_threshold=args.match_threshold,
                    weak_threshold=args.weak_threshold,
                )
            if args.once:
                break
    except KeyboardInterrupt:
        print()
        return 0
    except Exception as exc:
        print(f"error: microphone test failed: {exc}", file=sys.stderr)
        return 1

    return 0


def live_microphone_test(target_pitch_classes: list[int] | None = None) -> int:
    """Small callable wrapper for notebooks or experiments."""

    args = []
    if target_pitch_classes is not None:
        args.extend(["--target", ",".join(str(value) for value in target_pitch_classes)])
    return main_with_args(args)


def main_with_args(argv: list[str]) -> int:
    original_argv = sys.argv
    try:
        sys.argv = [original_argv[0], *argv]
        return main()
    finally:
        sys.argv = original_argv


def capture_and_detect(
    sounddevice_module,
    *,
    sample_rate: int,
    seconds: float,
    hop_length: int,
    device,
    chroma_method: str,
    silence_threshold: float,
) -> dict:
    frames = max(1, int(seconds * sample_rate))
    capture = sounddevice_module.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=device,
    )
    sounddevice_module.wait()
    samples = capture[:, 0].copy()
    chord = detect_chord(
        samples,
        sample_rate,
        noise_threshold=silence_threshold,
    )
    sequence = extract_audio_chroma(
        samples,
        sample_rate,
        hop_length=hop_length,
        method=chroma_method,
        silence_threshold=silence_threshold,
    )
    heard = average_active_chroma(sequence.chroma)
    return {"chord": chord, "heard": heard}


def capture_and_compare(
    sounddevice_module,
    target: np.ndarray,
    *,
    sample_rate: int,
    seconds: float,
    hop_length: int,
    device,
    chroma_method: str,
    silence_threshold: float,
) -> tuple[float, np.ndarray]:
    detection = capture_and_detect(
        sounddevice_module,
        sample_rate=sample_rate,
        seconds=seconds,
        hop_length=hop_length,
        device=device,
        chroma_method=chroma_method,
        silence_threshold=silence_threshold,
    )
    heard = detection["heard"]
    similarity = float(cosine_similarity_rows(heard.reshape(1, 12), target.reshape(1, 12))[0])
    return similarity, heard


def print_free_detection(detection: dict) -> None:
    chord = detection["chord"]
    heard_label = top_pitch_classes(detection["heard"], count=5, minimum=0.05) or "-"
    print(
        f"{time.strftime('%H:%M:%S')}  "
        f"chord={chord.chord_name:10s}  "
        f"conf={chord.confidence:.3f}  "
        f"rms={chord.rms:.4f}  "
        f"heard=[{heard_label}]"
    )


def print_target_comparison(
    detection: dict,
    target: np.ndarray,
    *,
    match_threshold: float,
    weak_threshold: float,
) -> None:
    heard = detection["heard"]
    similarity = float(cosine_similarity_rows(heard.reshape(1, 12), target.reshape(1, 12))[0])
    status = status_for_similarity(
        similarity,
        match_threshold=match_threshold,
        weak_threshold=weak_threshold,
    )
    heard_label = top_pitch_classes(heard, count=4, minimum=0.05) or "-"
    print(
        f"{time.strftime('%H:%M:%S')}  "
        f"similarity={similarity:.3f}  "
        f"status={status.replace('_', ' '):12s}  "
        f"heard=[{heard_label}]"
    )


def average_active_chroma(chroma: np.ndarray) -> np.ndarray:
    if len(chroma) == 0:
        return np.zeros(12, dtype=np.float64)
    norms = np.linalg.norm(chroma, axis=1)
    active = chroma[norms > 1e-12]
    if len(active) == 0:
        return np.zeros(12, dtype=np.float64)
    average = np.mean(active, axis=0)
    norm = np.linalg.norm(average)
    if norm <= 1e-12:
        return np.zeros(12, dtype=np.float64)
    return average / norm


def parse_pitch_classes(text: str) -> list[int]:
    cleaned = (
        text.replace("[", " ")
        .replace("]", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace(",", " ")
    )
    classes: list[int] = []
    for token in cleaned.split():
        upper = token.upper()
        if upper in NOTE_TO_PC:
            classes.append(NOTE_TO_PC[upper])
            continue
        try:
            value = int(token)
        except ValueError as exc:
            raise ValueError(f"invalid pitch class {token!r}; use 0-11 or names like C,E,G") from exc
        if not 0 <= value <= 11:
            raise ValueError(f"pitch class {value} is outside 0-11")
        classes.append(value)
    if not classes:
        raise ValueError("no pitch classes provided")
    return sorted(set(classes))


def pitch_class_vector(pitch_classes: list[int]) -> np.ndarray:
    vector = np.zeros(12, dtype=np.float64)
    for pitch_class in pitch_classes:
        vector[int(pitch_class) % 12] = 1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def parse_device(device: str | None):
    if device is None:
        return None
    try:
        return int(device)
    except ValueError:
        return device


if __name__ == "__main__":
    raise SystemExit(main())
