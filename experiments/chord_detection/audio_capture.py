"""
audio_capture.py
Handles capturing audio from a chosen device.
Uses sounddevice for normal devices, parec for PipeWire monitors.
"""

import subprocess
import threading
import time

import numpy as np
import sounddevice as sd


class ParecStream:
    """Captures audio by running parec (PipeWire/PulseAudio) and reading its stdout."""

    def __init__(self, device_name, sample_rate, block_duration, callback):
        self.callback = callback
        self.sample_rate = sample_rate
        self.block_size = int(sample_rate * block_duration)
        self.process = None
        self.thread = None
        self.running = False

        # Build the parec command
        cmd = [
            "parec",
            "--device",
            device_name,
            "--format",
            "s16le",
            "--rate",
            str(sample_rate),
            "--channels",
            "1",
            "--latency-msec",
            "10",
        ]
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _read_loop(self):
        bytes_per_chunk = self.block_size * 2  # 16-bit = 2 bytes
        while self.running:
            raw = self.process.stdout.read(bytes_per_chunk)
            if not raw:
                break
            # Convert s16le to float numpy array
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            self.callback(samples, self.sample_rate)

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def close(self):
        self.stop()


def start_stream(callback, sample_rate=48000, block_duration=0.1, device=None):
    """
    Start an audio input stream that calls `callback(indata_1d, sample_rate)`
    every `block_duration` seconds.

    Parameters:
    - callback: function(indata, sample_rate)
    - sample_rate: Hz (default 48000 to match most PipeWire setups)
    - block_duration: seconds
    - device: str or int or None. If None, auto-detect monitor source.
    """
    if device is None:
        # auto-detect: try common monitor name or fallback
        device = _find_monitor()
        if device is None:
            print("No monitor source found. Using default mic.")
            device = sd.default.device[0]

    # If device is a string that looks like a PipeWire monitor, use parec
    if isinstance(device, str) and ("monitor" in device.lower()):
        print(f"Using parec for device: {device}")
        return ParecStream(device, sample_rate, block_duration, callback)

    # Otherwise, use sounddevice
    block_size = int(sample_rate * block_duration)

    def audio_callback(indata, frames, time, status):
        mono = indata[:, 0].copy().flatten()
        callback(mono, sample_rate)

    stream = sd.InputStream(
        samplerate=sample_rate,
        blocksize=block_size,
        channels=1,
        device=device,
        callback=audio_callback,
    )
    stream.start()
    return stream


def _find_monitor():
    """Try to find a monitor source from PipeWire (via pactl)."""
    try:
        output = subprocess.check_output(
            ["pactl", "list", "sources", "short"], text=True
        )
        for line in output.strip().split("\n"):
            if "monitor" in line.lower():
                # The full monitor name is the second column
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]  # e.g., alsa_output.pci-...monitor
    except Exception:
        pass
    return None
