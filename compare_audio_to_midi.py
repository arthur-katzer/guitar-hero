#!/usr/bin/env python3
"""Offline chroma comparison between an audio file and a MIDI reference."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from audio.chroma_compare import (
    DEFAULT_HOP_LENGTH,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_DTW_CELLS,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_WEAK_THRESHOLD,
    compare_chroma,
    extract_audio_chroma,
    generate_report,
    load_audio,
    midi_to_chroma,
    plot_similarity,
    write_csv_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare an audio performance against a MIDI reference using chroma features."
    )
    parser.add_argument("--audio", required=True, help="Path to MP3/WAV/FLAC/OGG audio")
    parser.add_argument("--midi", required=True, help="Path to reference MIDI file")
    parser.add_argument("--out", default="artifacts/chroma_report.csv", help="CSV report path")
    parser.add_argument(
        "--plot",
        default=None,
        help="PNG plot path. Defaults to the CSV path with .png extension.",
    )
    parser.add_argument("--no-plot", action="store_true", help="Skip PNG plot generation")
    parser.add_argument(
        "--alignment",
        choices=["fixed", "dtw"],
        default="fixed",
        help="Use fixed-time comparison or dynamic time warping",
    )
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--hop-length", type=int, default=DEFAULT_HOP_LENGTH)
    parser.add_argument("--chroma-method", choices=["cqt", "stft"], default="cqt")
    parser.add_argument("--silence-threshold", type=float, default=0.001)
    parser.add_argument("--match-threshold", type=float, default=DEFAULT_MATCH_THRESHOLD)
    parser.add_argument("--weak-threshold", type=float, default=DEFAULT_WEAK_THRESHOLD)
    parser.add_argument("--dtw-max-cells", type=int, default=DEFAULT_MAX_DTW_CELLS)
    parser.add_argument("--include-drums", action="store_true", help="Include MIDI channel 10 percussion")
    parser.add_argument(
        "--max-segments",
        type=int,
        default=30,
        help="Maximum number of timeline segments printed to the terminal",
    )
    args = parser.parse_args()

    try:
        print(f"Loading audio: {args.audio}")
        audio, sample_rate = load_audio(args.audio, sample_rate=args.sample_rate)
        print(f"Extracting audio chroma at {sample_rate} Hz, hop={args.hop_length}")
        audio_sequence = extract_audio_chroma(
            audio,
            sample_rate,
            hop_length=args.hop_length,
            method=args.chroma_method,
            silence_threshold=args.silence_threshold,
        )

        frame_rate = sample_rate / float(args.hop_length)
        print(f"Loading MIDI: {args.midi}")
        if args.alignment == "fixed":
            midi_sequence = midi_to_chroma(
                args.midi,
                times=audio_sequence.times,
                include_drums=args.include_drums,
            )
        else:
            midi_sequence = midi_to_chroma(
                args.midi,
                frame_rate=frame_rate,
                include_drums=args.include_drums,
            )

        print(f"Comparing chroma with {args.alignment} alignment")
        result = compare_chroma(
            audio_sequence,
            midi_sequence,
            alignment=args.alignment,
            match_threshold=args.match_threshold,
            weak_threshold=args.weak_threshold,
            max_dtw_cells=args.dtw_max_cells,
        )

        write_csv_report(args.out, result)
        plot_path = Path(args.plot) if args.plot else Path(args.out).with_suffix(".png")
        if not args.no_plot:
            plot_similarity(
                plot_path,
                result,
                match_threshold=args.match_threshold,
                weak_threshold=args.weak_threshold,
            )

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    segments = generate_report(result)
    counts = _status_counts(result)
    print()
    print("Chroma comparison summary")
    print(f"  alignment: {result.alignment}")
    print(f"  frames: {len(result.rows)}")
    print(f"  mean cosine similarity: {result.mean_similarity:.3f}")
    print(f"  similarity percent: {result.similarity_percent:.1f}%")
    print(
        "  statuses: "
        + ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
    )
    print(f"  csv: {args.out}")
    if not args.no_plot:
        print(f"  plot: {plot_path}")

    print()
    print("Timeline")
    for segment in segments[: args.max_segments]:
        print(f"  {segment.to_text()}")
    if len(segments) > args.max_segments:
        print(f"  ... {len(segments) - args.max_segments} more segments in the CSV")

    return 0


def _status_counts(result) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in result.rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
