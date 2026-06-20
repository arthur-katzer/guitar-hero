"""Small audio decoding helpers.

This module is intentionally narrow: it gives the chroma comparison fallback a
way to read audio without pulling the old learning-lab CLI back into the repo.
"""

from __future__ import annotations

import math
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

DEFAULT_DECODE_SAMPLE_RATE = 22050


class AudioLoadError(RuntimeError):
    """Raised when an audio file cannot be decoded."""


def load_audio(
    path: str | Path,
    *,
    sample_rate: int | None = None,
) -> tuple[np.ndarray, int]:
    """Load an audio file as mono float samples plus sample rate.

    WAV files are read directly. Other formats are decoded through ffmpeg into
    mono float32 PCM. When `sample_rate` is omitted for non-WAV files, decoding
    uses `DEFAULT_DECODE_SAMPLE_RATE` so this path does not depend on ffprobe.
    """
    audio_path = Path(path)
    if not audio_path.exists():
        raise AudioLoadError(f"Audio file not found: {audio_path}")
    if sample_rate is not None and sample_rate <= 0:
        raise AudioLoadError("sample_rate must be positive")

    if audio_path.suffix.lower() == ".wav":
        source_rate, samples = wavfile.read(audio_path)
        mono = _to_mono_float(samples)
        if sample_rate is None or int(source_rate) == int(sample_rate):
            return mono, int(source_rate)
        return _resample(mono, int(source_rate), int(sample_rate)), int(sample_rate)

    decode_rate = int(sample_rate or DEFAULT_DECODE_SAMPLE_RATE)
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(decode_rate),
        "-",
    ]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise AudioLoadError(
            "ffmpeg is required for non-WAV files. Install imageio-ffmpeg, "
            "install ffmpeg on PATH, or use a WAV file."
        ) from exc
    except Exception as exc:
        raise AudioLoadError(
            f"Could not decode {audio_path}. ffmpeg stderr: {_stderr_text(exc)}"
        ) from exc

    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    return np.nan_to_num(samples, copy=False), decode_rate


def find_ffmpeg() -> str:
    """Return a usable ffmpeg executable path."""

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

    raise AudioLoadError(
        "ffmpeg not found. Install `imageio-ffmpeg` with "
        "`python -m pip install imageio-ffmpeg`, or install ffmpeg on PATH."
    )


def _to_mono_float(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples)
    if array.dtype.kind in {"i", "u"}:
        max_value = np.iinfo(array.dtype).max
        array = array.astype(np.float32) / float(max_value)
    else:
        array = array.astype(np.float32)
    if array.ndim == 2:
        array = np.mean(array, axis=1)
    return np.nan_to_num(array, copy=False)


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate <= 0 or target_rate <= 0:
        raise AudioLoadError("sample rates must be positive")
    if source_rate == target_rate:
        return samples.astype(np.float32, copy=False)
    try:
        from scipy.signal import resample_poly
    except ImportError as exc:
        raise AudioLoadError("scipy is required to resample WAV files") from exc

    common = math.gcd(int(source_rate), int(target_rate))
    up = int(target_rate) // common
    down = int(source_rate) // common
    return np.nan_to_num(resample_poly(samples, up, down).astype(np.float32), copy=False)


def _stderr_text(exc: Exception) -> str:
    stderr = getattr(exc, "stderr", "")
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace").strip()
    return str(stderr).strip()
