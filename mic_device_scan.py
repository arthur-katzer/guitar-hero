#!/usr/bin/env python3
"""Scan audio input devices and report whether Python receives signal."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
import time

import numpy as np
from scipy.io import wavfile

from audio.device_select import find_system_audio_device
from audio.dsp import analyze_pitch


@dataclass(frozen=True)
class DeviceScanResult:
    device: int
    name: str
    hostapi: str
    sample_rate: int
    channels: int
    duration_sec: float
    rms: float
    peak: float
    mean: float
    clipping_ratio: float
    detected_note: str
    detected_midi: int | None
    confidence: float
    status: str
    wav_path: str
    error: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record short clips from input devices and report signal level/pitch diagnostics."
    )
    parser.add_argument("--list-devices", action="store_true", help="List sounddevice audio devices")
    parser.add_argument(
        "--devices",
        help="Comma-separated device indexes to scan. Defaults to all input devices.",
    )
    parser.add_argument(
        "--system-audio",
        action="store_true",
        help="Scan only Windows Stereo Mix/Mixagem estéreo when available",
    )
    parser.add_argument("--seconds", type=float, default=2.0, help="Seconds to record from each device")
    parser.add_argument("--sample-rate", type=int, default=48000, help="Requested sample rate")
    parser.add_argument("--channels", type=int, default=1, help="Requested input channels")
    parser.add_argument("--threshold", type=float, default=0.005, help="RMS level considered audible")
    parser.add_argument("--output-dir", default="artifacts/mic_scan", help="Where WAV/CSV outputs go")
    parser.add_argument("--no-save", action="store_true", help="Do not save captured WAV files")
    parser.add_argument(
        "--countdown",
        type=float,
        default=1.5,
        help="Seconds to wait before each recording so you can start playback",
    )
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
        devices = selected_input_devices(sd, args.devices, args.system_audio)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not devices:
        print("error: no input devices found", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    if not args.no_save:
        output_dir.mkdir(parents=True, exist_ok=True)

    print("Mic device scan")
    print(f"  devices: {', '.join(str(index) for index in devices)}")
    print(f"  record time: {args.seconds:.2f}s per device")
    print(f"  sample rate: {args.sample_rate} Hz")
    print("Play your A4.mp3 near the mic during each recording.")
    print()

    results: list[DeviceScanResult] = []
    hostapis = sd.query_hostapis()
    for device_index in devices:
        info = sd.query_devices(device_index)
        hostapi_name = hostapis[int(info["hostapi"])]["name"]
        wav_path = "" if args.no_save else str(output_dir / f"device_{device_index}.wav")
        print(f"Device {device_index}: {info['name']} ({hostapi_name})")
        if args.countdown > 0:
            print(f"  recording in {args.countdown:.1f}s...")
            time.sleep(args.countdown)

        try:
            result = scan_device(
                sd,
                device_index,
                str(info["name"]),
                str(hostapi_name),
                sample_rate=args.sample_rate,
                channels=args.channels,
                seconds=args.seconds,
                threshold=args.threshold,
                wav_path=wav_path,
            )
        except Exception as exc:
            result = DeviceScanResult(
                device=device_index,
                name=str(info["name"]),
                hostapi=str(hostapi_name),
                sample_rate=args.sample_rate,
                channels=args.channels,
                duration_sec=args.seconds,
                rms=0.0,
                peak=0.0,
                mean=0.0,
                clipping_ratio=0.0,
                detected_note="Error",
                detected_midi=None,
                confidence=0.0,
                status="error",
                wav_path=wav_path,
                error=str(exc),
            )

        results.append(result)
        print_result(result)
        print()

    write_csv(output_dir / "summary.csv", results)
    best = best_result(results)
    if best is not None:
        print("Best signal")
        print_result(best)
    print(f"CSV summary: {output_dir / 'summary.csv'}")
    return 0


def scan_device(
    sounddevice_module,
    device_index: int,
    name: str,
    hostapi: str,
    *,
    sample_rate: int,
    channels: int,
    seconds: float,
    threshold: float,
    wav_path: str,
) -> DeviceScanResult:
    frames = max(1, int(sample_rate * seconds))
    capture = sounddevice_module.rec(
        frames,
        samplerate=sample_rate,
        channels=channels,
        dtype="float32",
        device=device_index,
    )
    sounddevice_module.wait()
    samples = np.asarray(capture, dtype=np.float32)
    mono = to_mono(samples)

    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64)))) if len(mono) else 0.0
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    mean = float(np.mean(mono)) if len(mono) else 0.0
    clipping_ratio = float(np.mean(np.abs(mono) >= 0.98)) if len(mono) else 0.0
    detection = analyze_pitch(mono, sample_rate, noise_threshold=max(0.0001, threshold / 5.0))
    status = classify_signal(rms, peak, threshold)

    if wav_path:
        save_wav(wav_path, mono, sample_rate)

    return DeviceScanResult(
        device=device_index,
        name=name,
        hostapi=hostapi,
        sample_rate=sample_rate,
        channels=channels,
        duration_sec=seconds,
        rms=rms,
        peak=peak,
        mean=mean,
        clipping_ratio=clipping_ratio,
        detected_note=detection.note_name,
        detected_midi=detection.midi,
        confidence=detection.confidence,
        status=status,
        wav_path=wav_path,
    )


def selected_input_devices(sounddevice_module, devices_text: str | None, system_audio: bool = False) -> list[int]:
    if devices_text and system_audio:
        raise RuntimeError("use either --devices or --system-audio, not both")
    if system_audio:
        device = find_system_audio_device(sounddevice_module)
        if device is None:
            raise RuntimeError(
                "could not find Stereo Mix/Mixagem estéreo. Enable Stereo Mix in Windows "
                "recording devices, or pass --devices manually."
            )
        return [device]

    if devices_text:
        return [int(token.strip()) for token in devices_text.split(",") if token.strip()]

    devices = sounddevice_module.query_devices()
    indexes: list[int] = []
    for index, info in enumerate(devices):
        if int(info.get("max_input_channels", 0)) > 0:
            indexes.append(index)
    return indexes


def classify_signal(rms: float, peak: float, threshold: float) -> str:
    if peak < 0.001:
        return "digital_silence"
    if rms < threshold:
        return "very_quiet"
    if peak > 0.98:
        return "clipping_risk"
    return "usable_signal"


def best_result(results: list[DeviceScanResult]) -> DeviceScanResult | None:
    usable = [result for result in results if result.status != "error"]
    if not usable:
        return None
    return max(usable, key=lambda result: (result.rms, result.peak))


def print_result(result: DeviceScanResult) -> None:
    if result.error:
        print(f"  status: {result.status}")
        print(f"  error: {result.error}")
        return
    print(f"  status: {result.status}")
    print(f"  rms: {result.rms:.6f}")
    print(f"  peak: {result.peak:.6f}")
    print(f"  note: {result.detected_note}")
    print(f"  confidence: {result.confidence:.3f}")
    if result.wav_path:
        print(f"  wav: {result.wav_path}")


def write_csv(path: Path, results: list[DeviceScanResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(asdict(results[0]).keys()) if results else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def save_wav(path: str, samples: np.ndarray, sample_rate: int) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    wavfile.write(output_path, sample_rate, (clipped * 32767).astype(np.int16))


def to_mono(samples: np.ndarray) -> np.ndarray:
    array = np.asarray(samples)
    if array.ndim == 2:
        array = np.mean(array, axis=1)
    return np.nan_to_num(array.astype(np.float32), copy=False)


if __name__ == "__main__":
    raise SystemExit(main())
