"""
main.py
Real‑time chord detector from system audio (or mic).
Usage:
    python main.py                 # auto‑detect monitor source
    python main.py list            # show available devices
    python main.py 3               # use device index 3
"""

import sys
import time

import sounddevice as sd

from audio_capture import start_stream
from chord_detector import detect_chord

last_chord = None
last_print_time = 0


def process_chunk(audio_chunk, sample_rate):
    global last_chord, last_print_time
    chord, confidence = detect_chord(audio_chunk, sample_rate)
    current_time = time.time()
    if chord != last_chord or (current_time - last_print_time > 0.5):
        print(f"{chord} (conf: {confidence:.2f})")
        last_chord = chord
        last_print_time = current_time


def list_devices():
    print("Available sound devices:")
    print(sd.query_devices())


def main():
    device = None  # None means auto‑detect

    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            list_devices()
            return
        else:
            try:
                device = int(sys.argv[1])
                print(f"Using device index {device}")
            except ValueError:
                device = sys.argv[1]  # try as string name
                print(f"Using device '{device}'")

    print("Starting chord detector. Play audio (e.g., YouTube) now...")
    print("Press Ctrl+C to stop.\n")

    stream = start_stream(
        process_chunk, sample_rate=48000, block_duration=0.1, device=device
    )

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped.")
        stream.stop()
        stream.close()


if __name__ == "__main__":
    main()
