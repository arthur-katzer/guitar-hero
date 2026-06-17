"""Helpers for choosing audio input devices."""

from __future__ import annotations


SYSTEM_AUDIO_MARKERS = (
    "mixagem estereo",
    "mixagem estéreo",
    "stereo mix",
    "what u hear",
    "loopback",
)


def parse_device(device: str | None):
    if device is None:
        return None
    try:
        return int(device)
    except ValueError:
        return device


def find_system_audio_device(sounddevice_module) -> int | None:
    """Return the first input device that looks like system-output capture."""

    devices = sounddevice_module.query_devices()
    for index, info in enumerate(devices):
        if int(info.get("max_input_channels", 0)) <= 0:
            continue
        normalized = normalize_device_name(str(info.get("name", "")))
        if any(marker in normalized for marker in SYSTEM_AUDIO_MARKERS):
            return index
    return None


def normalize_device_name(name: str) -> str:
    return (
        name.casefold()
        .replace("é", "e")
        .replace("ê", "e")
        .replace("á", "a")
        .replace("ã", "a")
        .replace("ç", "c")
    )
