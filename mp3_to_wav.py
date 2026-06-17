#!/usr/bin/env python3
"""Convert an MP3 file to WAV using ffmpeg.

The script first tries the Python package `imageio-ffmpeg`, which bundles an
ffmpeg executable, then falls back to a system `ffmpeg` on PATH.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert MP3 audio to WAV")
    parser.add_argument("input", help="Input MP3 file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Output WAV file. Defaults to the input path with .wav extension.",
    )
    parser.add_argument("--sample-rate", type=int, default=22050, help="Output sample rate")
    parser.add_argument("--channels", type=int, default=1, help="Output channel count")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output if it exists")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".wav")

    try:
        convert_mp3_to_wav(
            input_path,
            output_path,
            sample_rate=args.sample_rate,
            channels=args.channels,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"converted: {_display_path(input_path)}")
    print(f"wav: {_display_path(output_path)}")
    return 0


def convert_mp3_to_wav(
    input_path: str | Path,
    output_path: str | Path,
    *,
    sample_rate: int = 22050,
    channels: int = 1,
    overwrite: bool = False,
) -> None:
    source = Path(input_path)
    target = Path(output_path)

    if not source.exists():
        raise FileNotFoundError(f"input file not found: {source}")
    if source.suffix.lower() != ".mp3":
        raise ValueError(f"expected an .mp3 input file, got: {source}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {target}. Use --overwrite to replace it.")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")

    ffmpeg = find_ffmpeg()
    target.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-i",
        str(source),
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-acodec",
        "pcm_s16le",
        str(target),
    ]
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg conversion failed")


def find_ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled:
            return bundled
    except ImportError:
        pass

    system = shutil.which("ffmpeg")
    if system:
        return system

    raise RuntimeError(
        "ffmpeg not found. Install `imageio-ffmpeg` with "
        "`python -m pip install imageio-ffmpeg`, or install ffmpeg on PATH."
    )


def _display_path(path: Path) -> str:
    return str(path).encode(sys.stdout.encoding or "utf-8", errors="backslashreplace").decode(
        sys.stdout.encoding or "utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
