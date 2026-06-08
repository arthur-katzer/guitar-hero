#!/usr/bin/env python3
"""Offline audio-to-note learning lab."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import subprocess

from audio.chords import detect_chord
from audio.dsp import analyze_pitch, analyze_windows, spectrum_peaks, summarize_audio
from audio.io import AudioLoadError, load_audio
from audio.matching import match_detections_to_chart


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Guitar Hero DSP lab")
    parser.add_argument("--file", required=True, help="WAV/MP3/FLAC/OGG audio file to analyze")
    parser.add_argument(
        "--mode",
        choices=["summary", "fft", "notes", "chord", "match"],
        default="notes",
        help="summary = audio basics, fft = one-window peak, notes = timeline, chord = chroma/template matching, match = offline chart matching",
    )
    parser.add_argument("--window-ms", type=float, default=100.0)
    parser.add_argument("--hop-ms", type=float, default=50.0)
    parser.add_argument(
        "--start-sec",
        type=float,
        default=0.0,
        help="Start time for fft mode. Useful when a file has lead-in silence.",
    )
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument(
        "--peaks",
        type=int,
        default=8,
        help="Number of strongest FFT peaks to print in fft mode.",
    )
    parser.add_argument(
        "--plot-out",
        help="Optional PNG path for fft mode spectrum visualization.",
    )
    parser.add_argument(
        "--open-plot",
        action="store_true",
        help="Open --plot-out after writing it. Requires a desktop opener such as xdg-open.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=80,
        help="Maximum note rows to print in notes mode. Use 0 for all rows.",
    )
    parser.add_argument("--json-out", help="Optional path to write structured JSON results")
    parser.add_argument("--chart", help="Chart JSON path for match mode")
    parser.add_argument("--hit-window", type=float, default=0.25, help="Seconds around chart event for match mode")
    parser.add_argument("--midi-tolerance", type=int, default=0, help="Allowed MIDI note error for match mode")
    parser.add_argument("--min-confidence", type=float, default=0.5, help="Minimum detection confidence for match mode")
    args = parser.parse_args()

    try:
        samples, sample_rate = load_audio(args.file)
    except AudioLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.mode == "summary":
        summary = summarize_audio(samples, sample_rate)
        print("Audio summary")
        print(f"  file: {args.file}")
        print(f"  sample_rate: {summary['sample_rate']} Hz")
        print(f"  samples: {summary['samples']}")
        print(f"  duration: {summary['duration_seconds']:.3f} s")
        print(f"  rms: {summary['rms']:.6f}")
        _write_json(args.json_out, summary)
        return 0

    if args.mode == "fft":
        window_size = max(1, int(sample_rate * args.window_ms / 1000.0))
        start_sample = max(0, int(sample_rate * args.start_sec))
        result = analyze_pitch(
            samples[start_sample : start_sample + window_size],
            sample_rate,
            start_time=args.start_sec,
            noise_threshold=args.threshold,
        )
        chunk = samples[start_sample : start_sample + window_size]
        peaks = spectrum_peaks(chunk, sample_rate, count=args.peaks)
        print("FFT/HPS one-window detection")
        print(f"  window: {result.start_time:.3f}-{result.end_time:.3f} s")
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
        if args.plot_out:
            _write_fft_plot(
                chunk,
                sample_rate,
                args.plot_out,
                title=f"{Path(args.file).name} [{result.start_time:.3f}-{result.end_time:.3f}s]",
                peaks=peaks,
            )
            print(f"\nwrote plot: {args.plot_out}")
            if args.open_plot:
                _open_file(args.plot_out)
        _write_json(
            args.json_out,
            {
                "detection": result.to_dict(),
                "peaks": [peak.to_dict() for peak in peaks],
            },
        )
        return 0

    if args.mode == "chord":
        window_size = max(1, int(sample_rate * args.window_ms / 1000.0))
        start_sample = max(0, int(sample_rate * args.start_sec))
        chunk = samples[start_sample : start_sample + window_size]
        result = detect_chord(
            chunk,
            sample_rate,
            start_time=args.start_sec,
            noise_threshold=args.threshold,
        )
        print("Chord one-window detection")
        print(f"  window: {result.start_time:.3f}-{result.end_time:.3f} s")
        print(f"  chord: {result.chord_name}")
        print(f"  confidence: {result.confidence:.3f}")
        print(f"  rms: {result.rms:.6f}")
        print("\nChroma vector")
        print("  note   energy")
        for note, energy in zip(
            ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"],
            result.chroma,
        ):
            print(f"  {note:3s}    {energy:.3f}")
        if args.plot_out:
            _write_chroma_plot(
                result.chroma,
                args.plot_out,
                title=f"{Path(args.file).name} [{result.start_time:.3f}-{result.end_time:.3f}s] -> {result.chord_name}",
            )
            print(f"\nwrote plot: {args.plot_out}")
            if args.open_plot:
                _open_file(args.plot_out)
        _write_json(args.json_out, result.to_dict())
        return 0

    if args.mode == "match":
        if not args.chart:
            print("error: --chart is required for match mode", file=sys.stderr)
            return 1
        try:
            chart = json.loads(Path(args.chart).read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"error: could not read chart: {exc}", file=sys.stderr)
            return 1
        chart_events = chart.get("events", [])
        detections = analyze_windows(
            samples,
            sample_rate,
            window_ms=args.window_ms,
            hop_ms=args.hop_ms,
            noise_threshold=args.threshold,
        )
        summary = match_detections_to_chart(
            chart_events,
            detections,
            hit_window=args.hit_window,
            midi_tolerance=args.midi_tolerance,
            min_confidence=args.min_confidence,
        )
        print("Offline chart matching")
        print(f"  audio: {args.file}")
        print(f"  chart: {args.chart}")
        print(f"  events: {summary.total_events}")
        print(f"  hits: {summary.hits}")
        print(f"  misses: {summary.misses}")
        print(f"  accuracy: {summary.accuracy:.3f}")
        print(f"  hit_window: +/-{summary.hit_window:.3f}s")
        print(f"  midi_tolerance: {summary.midi_tolerance}")
        print(f"  min_confidence: {summary.min_confidence:.3f}")
        print("\nFirst results")
        print("chart_t  exp     det_t   det     dt       conf   status")
        shown = summary.results if args.limit == 0 else summary.results[: args.limit]
        for result in shown:
            det_time = "-" if result.detected_time is None else f"{result.detected_time:6.3f}"
            det_note = "-" if result.detected_note is None else result.detected_note
            delta = "-" if result.time_delta is None else f"{result.time_delta:+7.3f}"
            print(
                f"{result.chart_time:7.3f}  {result.expected_note:6s}  "
                f"{det_time:>6s}  {det_note:6s}  {delta:>7s}  "
                f"{result.confidence:5.3f}  {result.status}"
            )
        if args.limit and len(summary.results) > args.limit:
            print(f"... showing {args.limit} of {len(summary.results)} rows. Use --limit 0 for all rows.")
        _write_json(args.json_out, summary.to_dict())
        return 0

    results = analyze_windows(
        samples,
        sample_rate,
        window_ms=args.window_ms,
        hop_ms=args.hop_ms,
        noise_threshold=args.threshold,
    )
    print("Note timeline")
    print("start-end        note    midi    hz        cents    conf    rms")
    printed_results = results if args.limit == 0 else results[: args.limit]
    for result in printed_results:
        midi = "-" if result.midi is None else str(result.midi)
        hz = "-" if result.frequency_hz == 0 else f"{result.frequency_hz:7.2f}"
        cents = "-" if result.midi is None else f"{result.cents:+7.2f}"
        print(
            f"{result.start_time:6.3f}-{result.end_time:6.3f}  "
            f"{result.note_name:7s} {midi:>4s}  {hz:>7s}  "
            f"{cents:>7s}  {result.confidence:6.3f}  {result.rms:.6f}"
        )
    if args.limit and len(results) > args.limit:
        print(f"... showing {args.limit} of {len(results)} rows. Use --limit 0 for all rows.")
    _write_json(args.json_out, [result.to_dict() for result in results])
    return 0


def _write_json(path: str | None, data) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nwrote JSON: {output_path}")


def _write_fft_plot(samples, sample_rate: int, path: str, *, title: str, peaks) -> None:
    try:
        os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "error: matplotlib is required for --plot-out. Install requirements.txt first."
        ) from exc

    array = np.asarray(samples, dtype=np.float32)
    if len(array) == 0:
        raise SystemExit("error: cannot plot an empty audio window")

    windowed = array * np.hanning(len(array))
    magnitude = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(windowed), 1.0 / sample_rate)
    mask = (freqs >= 20.0) & (freqs <= 2000.0)
    freqs = freqs[mask]
    magnitude = magnitude[mask]
    if len(magnitude) and np.max(magnitude) > 0:
        magnitude = magnitude / np.max(magnitude)

    fig, ax = plt.subplots(figsize=(14, 7), dpi=140)
    ax.plot(freqs, magnitude, linewidth=1.0, color="tab:blue")
    ax.set_title(f"FFT Spectrum - {title}")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Relative magnitude")
    ax.set_xlim(20, 2000)
    ax.set_ylim(0, 1.05)
    ax.set_yticks(np.arange(0.0, 1.1, 0.1))
    ax.set_yticklabels([f"{value:.1f}" for value in np.arange(0.0, 1.1, 0.1)])

    major_ticks = [
        (20.0, "20"),
        (55.0, "A1\n55"),
        (82.41, "E2\n82"),
        (110.0, "A2\n110"),
        (146.83, "D3\n147"),
        (196.0, "G3\n196"),
        (246.94, "B3\n247"),
        (329.63, "E4\n330"),
        (440.0, "A4\n440"),
        (587.33, "D5\n587"),
        (783.99, "G5\n784"),
        (1046.5, "C6\n1047"),
        (1396.91, "F6\n1397"),
        (1760.0, "A6\n1760"),
        (2000.0, "2000"),
    ]
    ax.set_xticks([tick for tick, _ in major_ticks])
    ax.set_xticklabels([label for _, label in major_ticks], fontsize=8)
    ax.set_xticks(np.arange(100, 2000, 100), minor=True)
    ax.tick_params(axis="x", which="major", length=7)
    ax.tick_params(axis="x", which="minor", length=3)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(True, which="major", alpha=0.35)
    ax.grid(True, which="minor", axis="x", alpha=0.12)

    for peak in peaks[:5]:
        if 20.0 <= peak.frequency_hz <= 2000.0:
            ax.axvline(peak.frequency_hz, color="tab:red", alpha=0.28, linewidth=1.0)
            ax.scatter(
                [peak.frequency_hz],
                [peak.relative_magnitude],
                color="tab:red",
                s=24,
                zorder=3,
            )
            label_y = min(0.98, peak.relative_magnitude + 0.08)
            ax.annotate(
                f"{peak.note_name}\n{peak.frequency_hz:.1f} Hz\nrel {peak.relative_magnitude:.2f}",
                xy=(peak.frequency_hz, peak.relative_magnitude),
                xytext=(peak.frequency_hz, label_y),
                textcoords="data",
                ha="center",
                va="bottom",
                fontsize=8,
                bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "tab:red", "alpha": 0.85},
                arrowprops={"arrowstyle": "-", "color": "tab:red", "alpha": 0.6},
            )

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def _write_chroma_plot(chroma, path: str, *, title: str) -> None:
    try:
        os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "error: matplotlib is required for --plot-out. Install requirements.txt first."
        ) from exc

    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    values = np.asarray(chroma, dtype=np.float64)
    fig, ax = plt.subplots(figsize=(10, 5), dpi=140)
    bars = ax.bar(notes, values, color="tab:green")
    ax.set_title(f"Chroma Energy - {title}")
    ax.set_xlabel("Pitch class")
    ax.set_ylabel("Normalized energy")
    ax.set_ylim(0, 1.05)
    ax.set_yticks(np.arange(0.0, 1.1, 0.1))
    ax.grid(True, axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        if value > 0.05:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                min(1.02, value + 0.03),
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def _open_file(path: str) -> None:
    try:
        subprocess.Popen(
            ["xdg-open", str(Path(path))],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("warning: xdg-open not found; plot was saved but not opened", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
