#!/usr/bin/env python3
"""Small Windows-friendly audio capture and pitch detection prototype.

The detector is intentionally simple: it uses an FFT peak inside a guitar-ish
frequency range, then converts that frequency to the nearest MIDI note name.
It is a good MVP for checking that the USB Audio CODEC input is working before
building a fuller rhythm-game note matcher.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path
import queue
import sys
import time

import numpy as np
from scipy.io import wavfile

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - helpful before dependencies exist
    sd = None


DEVICE_NAME_FRAGMENT = "USB Audio CODEC"
DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_CHANNELS = 1
MIN_GUITAR_HZ = 70.0
DIAGNOSTIC_MIN_HZ = 60.0
MAX_GUITAR_HZ = 1200.0
PITCH_MODE_DOMINANT = "dominant"
PITCH_MODE_FUNDAMENTAL = "fundamental"
PITCH_MODES = (PITCH_MODE_DOMINANT, PITCH_MODE_FUNDAMENTAL)
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
STANDARD_GUITAR_TUNING = [
    ("E2", 82.41),
    ("A2", 110.00),
    ("D3", 146.83),
    ("G3", 196.00),
    ("B3", 246.94),
    ("E4", 329.63),
]


@dataclass(frozen=True)
class FftPeak:
    """One visible peak in the FFT spectrum."""

    frequency_hz: float
    magnitude: float
    relative_percent: float
    midi: int
    note: str


@dataclass(frozen=True)
class FundamentalEstimate:
    """The pitch estimate chosen from visible FFT peaks."""

    peak: FftPeak
    confidence: float
    harmonic_multiples: tuple[int, ...]
    harmonic_peaks: tuple[FftPeak, ...]
    used_fallback: bool
    reason: str


def require_sounddevice() -> None:
    """Exit with a clear message when sounddevice is not installed."""
    if sd is None:
        print(
            "error: sounddevice is not installed. Run: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1)


def list_input_devices() -> None:
    """Print all devices that can record audio."""
    require_sounddevice()
    devices = sd.query_devices()
    print("Input devices:")
    for index, device in enumerate(devices):
        if int(device["max_input_channels"]) > 0:
            default_sr = int(float(device["default_samplerate"]))
            print(
                f"  [{index}] {device['name']} "
                f"inputs={device['max_input_channels']} default_sr={default_sr}"
            )
    default_index = default_input_device_index()
    if default_index is not None:
        default_device = sd.query_devices(default_index)
        print(f"Default input: [{default_index}] {default_device['name']}")


def find_input_device(name_fragment: str = DEVICE_NAME_FRAGMENT) -> tuple[int, dict]:
    """Return the best input device whose name contains the requested text.

    Name matching is intentionally ranked because Linux audio stacks can expose
    the same USB interface both as an ALSA hardware device and as a Pulse/PipeWire
    virtual source. The direct ``USB Audio CODEC`` hardware endpoint has been
    more stable for the old blocking-stream diagnostic path than the virtual
    ``PCM2902 Audio Codec Analog Stereo`` source.

    @author Codex - ranked CODEC matching to avoid unstable virtual source.
    """
    require_sounddevice()
    matches: list[tuple[int, dict]] = []
    for index, device in enumerate(sd.query_devices()):
        if int(device["max_input_channels"]) <= 0:
            continue
        if name_fragment.lower() in str(device["name"]).lower():
            matches.append((index, device))

    if not matches:
        print(f"error: input device containing {name_fragment!r} was not found.", file=sys.stderr)
        print(
            "Run `python -m audio_detection.cli.audio_pitch_detector --list-devices` "
            "to see available inputs.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    def rank(match: tuple[int, dict]) -> tuple[int, int]:
        _index, device = match
        name = str(device["name"]).casefold()
        if name.startswith("usb audio codec"):
            return (0, 0)
        if "hw:" in name:
            return (1, 0)
        return (2, 0)

    return sorted(matches, key=rank)[0]


def choose_input_device(device_fragment: str, device_index: int | None) -> tuple[int, dict]:
    """Choose an input device by explicit index or ranked name lookup.

    @author Codex - allowed live APD modes to target a stable device index.
    """

    if device_index is not None:
        return input_device_by_index(device_index)
    return find_input_device(device_fragment)


def default_input_device_index() -> int | None:
    """Return sounddevice's default input device index when one is configured."""
    require_sounddevice()
    default_device = sd.default.device
    try:
        input_index = default_device[0]
    except (TypeError, IndexError):
        input_index = default_device

    try:
        input_index = int(input_index)
    except (TypeError, ValueError):
        return None

    if input_index < 0:
        return None

    device = sd.query_devices(input_index)
    if int(device["max_input_channels"]) <= 0:
        return None
    return input_index


def input_device_by_index(device_index: int) -> tuple[int, dict]:
    """Return an input device by index, or exit with a helpful error."""
    require_sounddevice()
    try:
        device = sd.query_devices(device_index)
    except Exception as exc:
        print(f"error: audio device index {device_index} was not found: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if int(device["max_input_channels"]) <= 0:
        print(f"error: device [{device_index}] {device['name']} is not an input device.", file=sys.stderr)
        raise SystemExit(1)

    return device_index, device


def choose_sample_rate(device_index: int | None, requested_rate: int = DEFAULT_SAMPLE_RATE) -> int:
    """Prefer 48000 Hz, but fall back to the device default if opening it fails."""
    require_sounddevice()
    try:
        sd.check_input_settings(
            device=device_index,
            channels=DEFAULT_CHANNELS,
            samplerate=requested_rate,
        )
        return requested_rate
    except Exception:
        if device_index is None:
            device = sd.query_devices(kind="input")
        else:
            device = sd.query_devices(device_index)
        fallback = int(float(device["default_samplerate"]))
        print(f"warning: {requested_rate} Hz is unavailable; falling back to {fallback} Hz.")
        return fallback


def record_audio(
    seconds: float,
    output_path: Path,
    device_fragment: str,
    device_index: int | None = None,
) -> tuple[np.ndarray, int]:
    """Record mono float audio and save it as a WAV file."""
    require_sounddevice()
    device_index, device = choose_input_device(device_fragment, device_index)
    sample_rate = choose_sample_rate(device_index)
    frames = int(seconds * sample_rate)

    print(f"Recording from [{device_index}] {device['name']} at {sample_rate} Hz for {seconds:.1f}s...")
    audio = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=DEFAULT_CHANNELS,
        dtype="float32",
        device=device_index,
    )
    sd.wait()

    mono = np.asarray(audio, dtype=np.float32).reshape(-1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(output_path, sample_rate, mono)
    print(f"Saved WAV: {output_path}")
    return mono, sample_rate


def calculate_rms(samples: np.ndarray) -> float:
    """Return root-mean-square volume for one audio buffer."""
    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(mono) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))


def estimate_pitch_fft(
    samples: np.ndarray,
    sample_rate: int,
    *,
    min_hz: float = MIN_GUITAR_HZ,
    max_hz: float = MAX_GUITAR_HZ,
    rms_threshold: float = 0.01,
    pitch_mode: str = PITCH_MODE_FUNDAMENTAL,
) -> tuple[float | None, float]:
    """Estimate pitch with the selected FFT interpretation mode."""
    peaks, rms = find_fft_peaks(samples, sample_rate, count=8, min_hz=min_hz, max_hz=max_hz)
    if rms < rms_threshold or not peaks:
        return None, rms
    estimate = estimate_pitch_from_peaks(peaks, pitch_mode)
    return estimate.peak.frequency_hz, rms


def find_fft_peaks(
    samples: np.ndarray,
    sample_rate: int,
    *,
    count: int = 5,
    min_hz: float = DIAGNOSTIC_MIN_HZ,
    max_hz: float = MAX_GUITAR_HZ,
    min_separation_hz: float = 8.0,
) -> tuple[list[FftPeak], float]:
    """Return the strongest separated FFT peaks inside the requested range."""
    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(mono) == 0:
        return [], 0.0

    rms = calculate_rms(mono)

    # Remove DC offset so slow input drift does not become the strongest peak.
    mono = mono - float(np.mean(mono))
    window = np.hanning(len(mono))
    windowed = mono * window

    # Zero-padding makes the peak display easier to read. It does not create new
    # information, but it gives the parabolic interpolation a nicer grid.
    fft_size = max(32_768, 1 << (len(windowed) - 1).bit_length())
    spectrum = np.fft.rfft(windowed, n=fft_size)
    magnitudes = np.abs(spectrum)
    freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)

    mask = (freqs >= min_hz) & (freqs <= max_hz)
    if not np.any(mask):
        return [], rms

    local_maxima = np.zeros_like(magnitudes, dtype=bool)
    local_maxima[1:-1] = (magnitudes[1:-1] >= magnitudes[:-2]) & (magnitudes[1:-1] > magnitudes[2:])
    candidate_indices = np.where(mask & local_maxima)[0]
    if len(candidate_indices) == 0:
        masked_magnitudes = np.where(mask, magnitudes, 0.0)
        candidate_indices = np.array([int(np.argmax(masked_magnitudes))])

    candidate_indices = sorted(candidate_indices, key=lambda index: magnitudes[index], reverse=True)
    selected: list[tuple[float, float]] = []
    for peak_index in candidate_indices:
        if magnitudes[peak_index] <= 0:
            continue

        refined_index = parabolic_interpolation(magnitudes, int(peak_index))
        frequency = refined_index * sample_rate / fft_size
        if frequency < min_hz or frequency > max_hz:
            continue
        if any(abs(frequency - existing_frequency) < min_separation_hz for existing_frequency, _ in selected):
            continue

        selected.append((float(frequency), float(magnitudes[peak_index])))
        if len(selected) >= count:
            break

    if not selected:
        return [], rms

    max_magnitude = max(magnitude for _frequency, magnitude in selected)
    peaks: list[FftPeak] = []
    for frequency, magnitude in selected:
        midi, note = frequency_to_note(frequency)
        peaks.append(
            FftPeak(
                frequency_hz=frequency,
                magnitude=magnitude,
                relative_percent=100.0 * magnitude / max_magnitude,
                midi=midi,
                note=note,
            )
        )
    return peaks, rms


def parabolic_interpolation(magnitudes: np.ndarray, peak_index: int) -> float:
    """Return a fractional FFT-bin index using the peak and its two neighbors."""
    if peak_index <= 0 or peak_index >= len(magnitudes) - 1:
        return float(peak_index)

    left = float(magnitudes[peak_index - 1])
    center = float(magnitudes[peak_index])
    right = float(magnitudes[peak_index + 1])
    denominator = left - 2.0 * center + right
    if abs(denominator) < 1e-12:
        return float(peak_index)

    offset = 0.5 * (left - right) / denominator
    return float(peak_index + np.clip(offset, -1.0, 1.0))


def frequency_to_note(frequency_hz: float) -> tuple[int, str]:
    """Convert a frequency in Hz to the nearest MIDI note and note name."""
    midi = int(round(69 + 12 * math.log2(frequency_hz / 440.0)))
    note_name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return midi, f"{note_name}{octave}"


def analyze_and_print(samples: np.ndarray, sample_rate: int, rms_threshold: float, pitch_mode: str) -> None:
    """Analyze one buffer or recording and print a human-readable result."""
    frequency, rms = estimate_pitch_fft(samples, sample_rate, rms_threshold=rms_threshold, pitch_mode=pitch_mode)
    if frequency is None:
        print(f"No stable pitch detected. RMS={rms:.5f}")
        return

    midi, note = frequency_to_note(frequency)
    print(f"Pitch mode: {pitch_mode}")
    print(f"Detected pitch: {frequency:8.2f} Hz | nearest note: {note} (MIDI {midi}) | RMS={rms:.5f}")


def harmonic_error(base_hz: float, harmonic_hz: float, multiple: int) -> float:
    """Return relative error for harmonic_hz compared to multiple * base_hz."""
    expected = base_hz * multiple
    if expected <= 0:
        return float("inf")
    return abs(harmonic_hz - expected) / expected


def find_harmonic_lock(
    peaks: list[FftPeak],
    *,
    tolerance: float = 0.03,
    min_relative_percent: float = 8.0,
) -> tuple[int, FftPeak] | None:
    """Detect whether the strongest peak may be a harmonic of a lower peak."""
    if len(peaks) < 2:
        return None

    dominant = peaks[0]
    best_match: tuple[float, int, FftPeak] | None = None
    for lower_peak in peaks[1:]:
        if lower_peak.frequency_hz >= dominant.frequency_hz:
            continue
        if lower_peak.relative_percent < min_relative_percent:
            continue

        for multiple in range(2, 6):
            error = harmonic_error(lower_peak.frequency_hz, dominant.frequency_hz, multiple)
            if error <= tolerance and (best_match is None or error < best_match[0]):
                best_match = (error, multiple, lower_peak)

    if best_match is None:
        return None
    _error, multiple, lower_peak = best_match
    return multiple, lower_peak


def harmonic_matches_for_peak(
    candidate: FftPeak,
    peaks: list[FftPeak],
    *,
    tolerance: float = 0.03,
    min_relative_percent: float = 8.0,
) -> list[tuple[int, FftPeak]]:
    """Find higher peaks that look like harmonics of a candidate fundamental."""
    matches: list[tuple[int, FftPeak]] = []
    for multiple in range(2, 6):
        possible_matches = [
            peak
            for peak in peaks
            if peak is not candidate
            and peak.frequency_hz > candidate.frequency_hz
            and peak.relative_percent >= min_relative_percent
            and harmonic_error(candidate.frequency_hz, peak.frequency_hz, multiple) <= tolerance
        ]
        if possible_matches:
            best_peak = min(
                possible_matches,
                key=lambda peak: harmonic_error(candidate.frequency_hz, peak.frequency_hz, multiple),
            )
            matches.append((multiple, best_peak))
    return matches


def estimate_fundamental_from_peaks(
    peaks: list[FftPeak],
    *,
    tolerance: float = 0.03,
    min_candidate_percent: float = 12.0,
    min_harmonic_percent: float = 8.0,
    min_harmonic_matches: int = 2,
) -> FundamentalEstimate:
    """
    Choose the likely fundamental from FFT peaks.

    A guitar note often has harmonics that are louder than the fundamental.
    This function asks: "does a lower peak explain several higher peaks as
    2x, 3x, 4x, or 5x harmonics?" If yes, that lower peak is probably the note
    the player hears. If not, we keep the dominant FFT peak.
    """
    if not peaks:
        raise ValueError("estimate_fundamental_from_peaks requires at least one peak")

    dominant = peaks[0]
    best_peak = dominant
    best_matches: list[tuple[int, FftPeak]] = []
    best_score = 0.0

    # Testing candidates from low to high makes the debug story easier to read,
    # while the score still decides the final answer.
    candidates = sorted(peaks, key=lambda peak: peak.frequency_hz)
    for candidate in candidates:
        if candidate.relative_percent < min_candidate_percent:
            continue

        matches = harmonic_matches_for_peak(
            candidate,
            peaks,
            tolerance=tolerance,
            min_relative_percent=min_harmonic_percent,
        )
        if len(matches) < min_harmonic_matches:
            continue

        harmonic_strength = sum(peak.relative_percent for _multiple, peak in matches)
        # Number of matching harmonics matters most. Strength breaks ties.
        # A tiny lower-frequency bonus nudges equal scores toward the fundamental.
        score = len(matches) * 100.0 + harmonic_strength + candidate.relative_percent - candidate.frequency_hz * 0.01
        if score > best_score:
            best_peak = candidate
            best_matches = matches
            best_score = score

    if best_matches:
        multiples = tuple(multiple for multiple, _peak in best_matches)
        harmonic_peaks = tuple(peak for _multiple, peak in best_matches)
        confidence = min(1.0, 0.45 + 0.15 * len(best_matches) + best_peak.relative_percent / 200.0)
        reason = f"{best_peak.frequency_hz:.1f} Hz explains harmonics at {format_multiples(multiples)}"
        return FundamentalEstimate(
            peak=best_peak,
            confidence=confidence,
            harmonic_multiples=multiples,
            harmonic_peaks=harmonic_peaks,
            used_fallback=False,
            reason=reason,
        )

    reason = "no strong harmonic relationship found; using dominant FFT peak"
    return FundamentalEstimate(
        peak=dominant,
        confidence=dominant.relative_percent / 100.0,
        harmonic_multiples=(),
        harmonic_peaks=(),
        used_fallback=True,
        reason=reason,
    )


def estimate_pitch_from_peaks(peaks: list[FftPeak], pitch_mode: str) -> FundamentalEstimate:
    """Select a pitch estimate using either the naive or harmonic-aware mode."""
    if not peaks:
        raise ValueError("estimate_pitch_from_peaks requires at least one peak")

    if pitch_mode == PITCH_MODE_DOMINANT:
        dominant = peaks[0]
        return FundamentalEstimate(
            peak=dominant,
            confidence=dominant.relative_percent / 100.0,
            harmonic_multiples=(),
            harmonic_peaks=(),
            used_fallback=True,
            reason="strongest FFT peak only",
        )

    if pitch_mode == PITCH_MODE_FUNDAMENTAL:
        return estimate_fundamental_from_peaks(peaks)

    raise ValueError(f"unknown pitch mode: {pitch_mode!r}")


def format_multiples(multiples: tuple[int, ...]) -> str:
    """Format harmonic numbers as 2x, 3x, 4x for debug output."""
    return ", ".join(f"{multiple}x" for multiple in multiples)


def choose_likely_fundamental(peaks: list[FftPeak]) -> FftPeak | None:
    """Prefer a lower peak when it explains multiple visible harmonics."""
    if not peaks:
        return None
    return estimate_fundamental_from_peaks(peaks).peak


def print_diagnosis_block(samples: np.ndarray, sample_rate: int, rms_threshold: float) -> None:
    """Print RMS, dominant peak, top peaks, and harmonic hints for one buffer."""
    peaks, rms = find_fft_peaks(
        samples,
        sample_rate,
        count=5,
        min_hz=DIAGNOSTIC_MIN_HZ,
        max_hz=MAX_GUITAR_HZ,
    )

    if rms < rms_threshold or not peaks:
        print(f"quiet / no pitch | RMS={rms:.5f}")
        return

    dominant = peaks[0]
    estimate = estimate_fundamental_from_peaks(peaks)
    print(f"RMS: {rms:.5f}")
    print(f"Dominant peak: {dominant.frequency_hz:6.1f} Hz | {dominant.note} | MIDI {dominant.midi}")
    print(
        f"Likely fundamental: {estimate.peak.frequency_hz:6.1f} Hz | "
        f"{estimate.peak.note} | MIDI {estimate.peak.midi}"
    )
    print()
    print("Top peaks:")
    for index, peak in enumerate(peaks, start=1):
        print(
            f"{index}. {peak.frequency_hz:6.1f} Hz | {peak.note:4s} | "
            f"MIDI {peak.midi:3d} | {peak.relative_percent:5.0f}%"
        )

    harmonic_lock = find_harmonic_lock(peaks)
    if harmonic_lock is not None:
        multiple, lower_peak = harmonic_lock
        print()
        print(
            "Possible harmonic lock: "
            f"{dominant.frequency_hz:.1f} Hz may be {multiple}x {lower_peak.frequency_hz:.1f} Hz"
        )

    print()
    print(f"Reason: {estimate.reason}")


def ordinal(number: int) -> str:
    """Return a small ordinal string for harmonic labels."""
    names = {2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
    return names.get(number, f"{number}th")


def describe_pitch_difference(dominant: FftPeak, estimate: FundamentalEstimate) -> str:
    """Explain how the naive dominant peak differs from the harmonic-aware pitch."""
    if dominant.midi == estimate.peak.midi:
        return "both modes picked the same note"

    for multiple in range(2, 6):
        if harmonic_error(estimate.peak.frequency_hz, dominant.frequency_hz, multiple) <= 0.03:
            return f"naive picked {ordinal(multiple)} harmonic"

    return "naive and harmonic-aware modes picked different notes"


def print_comparison_block(samples: np.ndarray, sample_rate: int, rms_threshold: float) -> None:
    """Print naive and harmonic-aware interpretations for one audio buffer."""
    peaks, rms = find_fft_peaks(
        samples,
        sample_rate,
        count=8,
        min_hz=DIAGNOSTIC_MIN_HZ,
        max_hz=MAX_GUITAR_HZ,
    )
    if rms < rms_threshold or not peaks:
        print(f"quiet / no pitch | RMS={rms:.5f}")
        return

    dominant = peaks[0]
    estimate = estimate_fundamental_from_peaks(peaks)
    print(f"RMS={rms:.5f}")
    print(f"Naive dominant:       {dominant.frequency_hz:6.1f} Hz | {dominant.note:4s} | MIDI {dominant.midi:3d}")
    print(
        f"Harmonic-aware pitch: {estimate.peak.frequency_hz:6.1f} Hz | "
        f"{estimate.peak.note:4s} | MIDI {estimate.peak.midi:3d}"
    )
    print(f"Difference: {describe_pitch_difference(dominant, estimate)}")


def print_mic_test_block(samples: np.ndarray, sample_rate: int, rms_threshold: float) -> None:
    """Print a compact pitch readout for a generic microphone input."""
    peaks, rms = find_fft_peaks(
        samples,
        sample_rate,
        count=8,
        min_hz=DIAGNOSTIC_MIN_HZ,
        max_hz=MAX_GUITAR_HZ,
    )
    if rms < rms_threshold or not peaks:
        print(f"quiet / no pitch | RMS={rms:.5f}")
        return

    dominant = peaks[0]
    estimate = estimate_fundamental_from_peaks(peaks)
    print(f"RMS={rms:.5f}")
    print(f"Dominant peak:      {dominant.frequency_hz:6.1f} Hz | {dominant.note:4s} | MIDI {dominant.midi:3d}")
    print(
        f"Likely fundamental: {estimate.peak.frequency_hz:6.1f} Hz | "
        f"{estimate.peak.note:4s} | MIDI {estimate.peak.midi:3d}"
    )
    print(f"Reason: {estimate.reason}")


def realtime(
    device_fragment: str,
    device_index: int | None,
    rms_threshold: float,
    buffer_ms: float,
    smooth_count: int,
    max_seconds: float | None = None,
    print_interval: float = 1.0,
    pitch_mode: str = PITCH_MODE_FUNDAMENTAL,
) -> None:
    """Continuously print smoothed frequency and note estimates from the input."""
    require_sounddevice()
    device_index, device = choose_input_device(device_fragment, device_index)
    sample_rate = choose_sample_rate(device_index)
    blocksize = int(sample_rate * buffer_ms / 1000.0)
    recent_notes: deque[int] = deque(maxlen=max(1, smooth_count))
    recent_freqs: deque[float] = deque(maxlen=max(1, smooth_count))
    last_printed_at = 0.0
    last_printed_status = ""

    print(f"Listening on [{device_index}] {device['name']} at {sample_rate} Hz. Press Ctrl+C to stop.")
    started_at = time.monotonic()
    try:
        while True:
            if max_seconds is not None and time.monotonic() - started_at >= max_seconds:
                print("Stopped after realtime smoke-test duration.")
                return

            capture = sd.rec(
                blocksize,
                samplerate=sample_rate,
                channels=DEFAULT_CHANNELS,
                dtype="float32",
                device=device_index,
            )
            sd.wait()
            block = np.asarray(capture, dtype=np.float32).reshape(-1)

            peaks, rms = find_fft_peaks(
                block,
                sample_rate,
                count=8,
                min_hz=MIN_GUITAR_HZ,
                max_hz=MAX_GUITAR_HZ,
            )
            if rms < rms_threshold or not peaks:
                recent_notes.clear()
                recent_freqs.clear()
                text = f"quiet / no pitch | RMS={rms:.5f}"
                now = time.monotonic()
                status = "quiet"
                if now - last_printed_at >= print_interval or status != last_printed_status:
                    print(text)
                    last_printed_at = now
                    last_printed_status = status
                continue

            dominant = peaks[0]
            estimate = estimate_pitch_from_peaks(peaks, pitch_mode)
            recent_notes.append(estimate.peak.midi)
            recent_freqs.append(estimate.peak.frequency_hz)

            # Median smoothing keeps one strange buffer from flipping the display.
            smooth_midi = int(round(float(np.median(recent_notes))))
            smooth_freq = float(np.median(recent_freqs))
            _smooth_midi, smooth_note = frequency_to_note(smooth_freq)
            if pitch_mode == PITCH_MODE_DOMINANT:
                text = "\n".join(
                    [
                        "Pitch mode: dominant",
                        f"Detected pitch: {smooth_freq:8.2f} Hz | {smooth_note:4s} | MIDI {smooth_midi:3d} | RMS={rms:.5f}",
                        f"Reason: {estimate.reason}",
                    ]
                )
            else:
                text = "\n".join(
                    [
                        "Pitch mode: fundamental",
                        f"Dominant peak:  {dominant.frequency_hz:8.2f} Hz | {dominant.note:4s} | MIDI {dominant.midi:3d} | RMS={rms:.5f}",
                        f"Detected pitch: {smooth_freq:8.2f} Hz | {smooth_note:4s} | MIDI {smooth_midi:3d}",
                        f"Reason: {estimate.reason}",
                    ]
                )
            now = time.monotonic()
            status = f"{pitch_mode}:{dominant.note}->{smooth_note}:{estimate.harmonic_multiples}"
            if now - last_printed_at >= print_interval or status != last_printed_status:
                print(text)
                last_printed_at = now
                last_printed_status = status
    except KeyboardInterrupt:
        print("\nStopped.")


def diagnose(
    device_fragment: str,
    device_index: int | None,
    rms_threshold: float,
    buffer_ms: float,
    max_seconds: float | None = None,
    print_interval: float = 1.0,
) -> None:
    """Continuously print FFT peaks so harmonic problems are visible."""
    require_sounddevice()
    device_index, device = choose_input_device(device_fragment, device_index)
    sample_rate = choose_sample_rate(device_index)

    # Longer windows make low guitar notes much easier to diagnose.
    diagnostic_buffer_ms = max(buffer_ms, 250.0)
    blocksize = int(sample_rate * diagnostic_buffer_ms / 1000.0)

    print(
        f"Diagnosing [{device_index}] {device['name']} at {sample_rate} Hz "
        f"with {diagnostic_buffer_ms:.0f} ms windows. Press Ctrl+C to stop."
    )
    started_at = time.monotonic()
    last_printed_at = 0.0
    blocks: queue.Queue[np.ndarray] = queue.Queue(maxsize=4)

    def on_audio(indata, _frames, _time_info, status) -> None:
        if status:
            print(f"warning: {status}")
        block = np.asarray(indata, dtype=np.float32).reshape(-1).copy()
        try:
            blocks.put_nowait(block)
        except queue.Full:
            _oldest = blocks.get_nowait()
            blocks.put_nowait(block)

    try:
        with sd.InputStream(
            device=device_index,
            channels=DEFAULT_CHANNELS,
            samplerate=sample_rate,
            blocksize=blocksize,
            dtype="float32",
            callback=on_audio,
        ):
            while True:
                if max_seconds is not None and time.monotonic() - started_at >= max_seconds:
                    print("Stopped after diagnostic smoke-test duration.")
                    return

                try:
                    block = blocks.get(timeout=0.1)
                except queue.Empty:
                    continue

                now = time.monotonic()
                if now - last_printed_at < print_interval:
                    continue

                print()
                print_diagnosis_block(block, sample_rate, rms_threshold)
                last_printed_at = now
    except KeyboardInterrupt:
        print("\nStopped.")


def compare_modes(
    device_fragment: str,
    device_index: int | None,
    rms_threshold: float,
    buffer_ms: float,
    max_seconds: float | None = None,
    print_interval: float = 1.0,
) -> None:
    """Continuously compare naive dominant peak and harmonic-aware pitch."""
    require_sounddevice()
    device_index, device = choose_input_device(device_fragment, device_index)
    sample_rate = choose_sample_rate(device_index)

    comparison_buffer_ms = max(buffer_ms, 250.0)
    blocksize = int(sample_rate * comparison_buffer_ms / 1000.0)

    print(
        f"Comparing pitch modes on [{device_index}] {device['name']} at {sample_rate} Hz "
        f"with {comparison_buffer_ms:.0f} ms windows. Press Ctrl+C to stop."
    )
    started_at = time.monotonic()
    last_printed_at = 0.0

    try:
        with sd.InputStream(
            device=device_index,
            channels=DEFAULT_CHANNELS,
            samplerate=sample_rate,
            blocksize=blocksize,
            dtype="float32",
        ) as stream:
            while True:
                if max_seconds is not None and time.monotonic() - started_at >= max_seconds:
                    print("Stopped after comparison duration.")
                    return

                block, overflowed = stream.read(blocksize)
                if overflowed:
                    print("warning: audio input overflow")

                now = time.monotonic()
                if now - last_printed_at < print_interval:
                    continue

                print()
                print_comparison_block(block[:, 0], sample_rate, rms_threshold)
                last_printed_at = now
    except KeyboardInterrupt:
        print("\nStopped.")


def mic_test(
    device_index: int | None,
    rms_threshold: float,
    buffer_ms: float,
    max_seconds: float | None = None,
    print_interval: float = 1.0,
) -> None:
    """Run pitch detection from an arbitrary/default microphone input."""
    require_sounddevice()
    list_input_devices()
    print()

    if device_index is None:
        stream_device_index = default_input_device_index()
        if stream_device_index is None:
            stream_device_index = None
            device = sd.query_devices(kind="input")
            device_label = f"default input ({device['name']})"
        else:
            device = sd.query_devices(stream_device_index)
            device_label = f"[{stream_device_index}] {device['name']} (default input)"
    else:
        stream_device_index, device = input_device_by_index(device_index)
        device_label = f"[{stream_device_index}] {device['name']}"

    sample_rate = choose_sample_rate(stream_device_index)
    mic_buffer_ms = max(buffer_ms, 250.0)
    blocksize = int(sample_rate * mic_buffer_ms / 1000.0)

    print(
        f"Mic test on {device_label} at {sample_rate} Hz "
        f"with {mic_buffer_ms:.0f} ms windows. Press Ctrl+C to stop."
    )
    started_at = time.monotonic()
    last_printed_at = 0.0

    try:
        with sd.InputStream(
            device=stream_device_index,
            channels=DEFAULT_CHANNELS,
            samplerate=sample_rate,
            blocksize=blocksize,
            dtype="float32",
        ) as stream:
            while True:
                if max_seconds is not None and time.monotonic() - started_at >= max_seconds:
                    print("Stopped after mic-test duration.")
                    return

                block, overflowed = stream.read(blocksize)
                if overflowed:
                    print("warning: audio input overflow")

                now = time.monotonic()
                if now - last_printed_at < print_interval:
                    continue

                print()
                print_mic_test_block(block[:, 0], sample_rate, rms_threshold)
                last_printed_at = now
    except KeyboardInterrupt:
        print("\nStopped.")


def print_guitar_reference() -> None:
    """Print standard guitar tuning note names and frequencies."""
    print("Standard guitar tuning:")
    for note, frequency in STANDARD_GUITAR_TUNING:
        print(f"{note} = {frequency:.2f} Hz")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture audio and estimate dominant guitar-note frequency.")
    parser.add_argument("--list-devices", action="store_true", help="List available audio input devices")
    parser.add_argument("--record", type=float, metavar="SECONDS", help="Record a WAV and analyze it")
    parser.add_argument("--realtime", action="store_true", help="Continuously estimate pitch from the input")
    parser.add_argument("--diagnose", action="store_true", help="Continuously print FFT peaks and harmonic warnings")
    parser.add_argument("--compare", action="store_true", help="Compare naive dominant and harmonic-aware pitch live")
    parser.add_argument("--mic-test", action="store_true", help="Test pitch detection from the default/input-index microphone")
    parser.add_argument("--guitar-reference", action="store_true", help="Print standard guitar tuning frequencies")
    parser.add_argument(
        "--pitch-mode",
        choices=PITCH_MODES,
        default=PITCH_MODE_FUNDAMENTAL,
        help="Pitch detector mode for --record and --realtime",
    )
    parser.add_argument("--device-name", default=DEVICE_NAME_FRAGMENT, help="Input device name fragment to search for")
    parser.add_argument("--device-index", type=int, help="Input device index for recording/live modes")
    parser.add_argument("--output", default="var/artifacts/recording.wav", help="Output WAV path for --record")
    parser.add_argument("--rms-threshold", type=float, default=0.01, help="Ignore audio quieter than this RMS")
    parser.add_argument("--buffer-ms", type=float, default=80.0, help="Realtime/diagnostic buffer length in milliseconds")
    parser.add_argument("--smooth-count", type=int, default=5, help="Number of recent detections used for smoothing")
    parser.add_argument("--max-seconds", type=float, help="Stop live modes after this many seconds, useful for tests")
    parser.add_argument(
        "--print-interval",
        type=float,
        default=1.0,
        help="Minimum seconds between realtime print updates",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.guitar_reference:
        print_guitar_reference()
        return 0

    if args.list_devices:
        list_input_devices()
        return 0

    if args.record is not None:
        samples, sample_rate = record_audio(args.record, Path(args.output), args.device_name, args.device_index)
        analyze_and_print(samples, sample_rate, args.rms_threshold, args.pitch_mode)
        return 0

    if args.realtime:
        realtime(
            args.device_name,
            args.device_index,
            args.rms_threshold,
            args.buffer_ms,
            args.smooth_count,
            args.max_seconds,
            args.print_interval,
            args.pitch_mode,
        )
        return 0

    if args.diagnose:
        diagnose(
            args.device_name,
            args.device_index,
            args.rms_threshold,
            args.buffer_ms,
            args.max_seconds,
            args.print_interval,
        )
        return 0

    if args.compare:
        compare_modes(
            args.device_name,
            args.device_index,
            args.rms_threshold,
            args.buffer_ms,
            args.max_seconds,
            args.print_interval,
        )
        return 0

    if args.mic_test:
        mic_test(
            args.device_index,
            args.rms_threshold,
            args.buffer_ms,
            args.max_seconds,
            args.print_interval,
        )
        return 0

    print(
        "Nothing to do. Try --list-devices, --record 3, --realtime, "
        "--diagnose, --compare, --mic-test, or --guitar-reference."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
