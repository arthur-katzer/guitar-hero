#!/usr/bin/env python3
"""Microphone/audio-interface capture lab for real instrument tests."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from scipy.io import wavfile
import sounddevice as sd

from audio.chords import detect_chord
from audio.dsp import analyze_pitch, spectrum_peaks


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture microphone/interface audio and analyze it")
    parser.add_argument("--list-devices", action="store_true", help="List sounddevice audio devices")
    parser.add_argument("--diagnose-wav", help="Analyze an existing WAV capture for level/signal problems")
    parser.add_argument("--seconds", type=float, default=3.0, help="Capture duration")
    parser.add_argument("--sample-rate", type=int, default=48000, help="Capture sample rate")
    parser.add_argument("--device", help="Input device index or name")
    parser.add_argument(
        "--mode",
        choices=["fft", "chord"],
        default="fft",
        help="Analyze captured audio as dominant pitch or chord",
    )
    parser.add_argument("--threshold", type=float, default=0.01, help="RMS silence threshold")
    parser.add_argument("--save-wav", default="artifacts/mic_capture.wav", help="Path to save captured WAV")
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        print(f"default device: {sd.default.device}")
        return 0

    if args.diagnose_wav:
        try:
            sample_rate, wav_samples = wavfile.read(args.diagnose_wav)
        except Exception as exc:
            print(f"error: could not read WAV: {exc}", file=sys.stderr)
            return 1
        samples = _wav_to_float(wav_samples)
        _print_signal_diagnostics(samples, sample_rate)
        return 0

    device = _parse_device(args.device)
    print(
        f"Recording {args.seconds:.2f}s at {args.sample_rate} Hz"
        + (f" from device {device!r}" if device is not None else " from default input")
    )
    print("Play the note/chord now.")
    try:
        capture = sd.rec(
            int(args.seconds * args.sample_rate),
            samplerate=args.sample_rate,
            channels=1,
            dtype="float32",
            device=device,
        )
        sd.wait()
    except Exception as exc:
        print(f"error: microphone capture failed: {exc}", file=sys.stderr)
        print("Run `python -m tools.mic_lab --list-devices` and check OS audio permissions.", file=sys.stderr)
        return 1

    samples = capture[:, 0].copy()
    _save_wav(args.save_wav, samples, args.sample_rate)
    print(f"saved WAV: {args.save_wav}")
    _print_signal_diagnostics(samples, args.sample_rate)

    if args.mode == "chord":
        result = detect_chord(samples, args.sample_rate, noise_threshold=args.threshold)
        print("Chord detection")
        print(f"  chord: {result.chord_name}")
        print(f"  confidence: {result.confidence:.3f}")
        print(f"  rms: {result.rms:.6f}")
        print("  chroma:")
        for note, energy in zip(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"], result.chroma):
            print(f"    {note:3s} {energy:.3f}")
        return 0

    result = analyze_pitch(samples, args.sample_rate, noise_threshold=args.threshold)
    peaks = spectrum_peaks(samples, args.sample_rate, count=8)
    print("Pitch detection")
    print(f"  note: {result.note_name}")
    print(f"  midi: {result.midi}")
    print(f"  peak_frequency: {result.peak_frequency_hz:.2f} Hz")
    print(f"  hps_frequency: {result.hps_frequency_hz:.2f} Hz")
    print(f"  cents: {result.cents:+.2f}")
    print(f"  confidence: {result.confidence:.3f}")
    print(f"  rms: {result.rms:.6f}")
    if peaks:
        print("\nStrongest FFT peaks")
        print("  rank    hz        rel_mag   note   midi")
        for idx, peak in enumerate(peaks, start=1):
            midi = "-" if peak.midi is None else str(peak.midi)
            print(
                f"  {idx:>4d}  {peak.frequency_hz:8.2f}   "
                f"{peak.relative_magnitude:7.3f}   {peak.note_name:5s}  {midi:>4s}"
            )
    return 0


def _parse_device(device: str | None):
    if device is None:
        return None
    try:
        return int(device)
    except ValueError:
        return device


def _save_wav(path: str, samples: np.ndarray, sample_rate: int) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    wavfile.write(output_path, sample_rate, (clipped * 32767).astype(np.int16))


def _wav_to_float(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples)
    if array.ndim == 2:
        array = np.mean(array, axis=1)
    if array.dtype.kind in {"i", "u"}:
        return array.astype(np.float32) / float(np.iinfo(array.dtype).max)
    return array.astype(np.float32)


def _print_signal_diagnostics(samples: np.ndarray, sample_rate: int) -> None:
    if len(samples) == 0:
        print("Signal diagnostics: empty capture")
        return

    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    peak = float(np.max(np.abs(samples)))
    mean = float(np.mean(samples))
    duration = len(samples) / float(sample_rate)
    clipping_ratio = float(np.mean(np.abs(samples) >= 0.98))

    print("\nSignal diagnostics")
    print(f"  duration: {duration:.3f}s")
    print(f"  sample_rate: {sample_rate} Hz")
    print(f"  rms: {rms:.6f}")
    print(f"  peak: {peak:.6f}")
    print(f"  dc_offset_mean: {mean:+.6f}")
    print(f"  clipping_ratio: {clipping_ratio:.6f}")

    if peak < 0.005:
        print("  diagnosis: near-silence. Wrong input device, muted input, or gain too low.")
    elif rms < 0.01:
        print("  diagnosis: very quiet. Increase interface/input gain or move mic closer.")
    elif clipping_ratio > 0.001 or peak > 0.98:
        print("  diagnosis: clipping risk. Lower interface/input gain.")
    elif abs(mean) > 0.02:
        print("  diagnosis: DC offset is high. Input chain may need correction/filtering.")
    else:
        print("  diagnosis: signal level looks usable for DSP.")


if __name__ == "__main__":
    raise SystemExit(main())
