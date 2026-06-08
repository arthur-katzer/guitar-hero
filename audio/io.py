"""Audio file loading helpers for the offline lab."""

from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np
from scipy.io import wavfile


class AudioLoadError(RuntimeError):
    """Raised when an audio file cannot be decoded."""


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """
    Load an audio file as mono-ish float samples plus sample rate.

    WAV files use scipy directly. Other formats are decoded by ffmpeg into
    mono float32 PCM.
    """
    audio_path = Path(path)
    if not audio_path.exists():
        raise AudioLoadError(f"Audio file not found: {audio_path}")

    if audio_path.suffix.lower() == ".wav":
        sample_rate, samples = wavfile.read(audio_path)
        return _normalize_samples(samples), int(sample_rate)

    cmd = [
        "ffmpeg",
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
        "-",
    ]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise AudioLoadError(
            "ffmpeg is required for non-WAV files. Install ffmpeg or use a WAV file."
        ) from exc
    except Exception as exc:
        raise AudioLoadError(
            f"Could not decode {audio_path}. ffmpeg stderr: {_stderr_text(exc)}"
        ) from exc

    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    sample_rate = _probe_sample_rate(audio_path)
    return _normalize_samples(samples), sample_rate


def _normalize_samples(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples)
    if array.dtype.kind in {"i", "u"}:
        max_value = np.iinfo(array.dtype).max
        return array.astype(np.float32) / float(max_value)
    return array.astype(np.float32)


def _probe_sample_rate(path: Path) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception as exc:
        raise AudioLoadError(f"Could not read sample rate with ffprobe: {_stderr_text(exc)}") from exc
    try:
        return int(proc.stdout.strip())
    except ValueError as exc:
        raise AudioLoadError(f"Invalid ffprobe sample rate output: {proc.stdout!r}") from exc


def _stderr_text(exc: Exception) -> str:
    stderr = getattr(exc, "stderr", "")
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace").strip()
    return str(stderr).strip()
