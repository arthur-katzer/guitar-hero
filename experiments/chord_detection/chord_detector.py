"""
chord_detector.py
Core logic: takes an audio chunk (numpy array of samples) and returns
the best matching chord name and a confidence score.
"""

import numpy as np

from chord_templates import TEMPLATES, get_chord_name

# Larger FFT size for better frequency resolution (zero-padding)
FFT_SIZE = 65536


def detect_chord(audio_chunk, sample_rate):
    """
    Analyze a chunk of audio and return (chord_name, confidence).

    Parameters:
    - audio_chunk: 1D numpy array of float samples
    - sample_rate: int, samples per second

    Returns:
    - chord_name: string
    - confidence: float between 0 and 1 (1 = perfect match)
    """

    if len(audio_chunk) == 0:
        return "Silence", 0.0

    # Apply Hann window
    window = np.hanning(len(audio_chunk))
    windowed_chunk = audio_chunk * window

    # Compute FFT with zero-padding
    fft_result = np.fft.rfft(windowed_chunk, n=FFT_SIZE)
    magnitude = np.abs(fft_result)

    # Frequency bins
    freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / sample_rate)

    # Chroma vector (12 pitch classes)
    chroma = np.zeros(12)

    for i in range(1, len(magnitude)):
        freq = freqs[i]
        if freq < 65:  # C2
            continue
        if freq > 2000:  # upper guitar range
            continue

        # Exact MIDI number
        midi_float = 12.0 * np.log2(freq / 440.0) + 69.0
        pitch_class = round(midi_float) % 12

        # Distance from pure semitone centre (0 = perfect, 0.5 = worst)
        distance = abs(midi_float - round(midi_float))
        weight = max(0.0, 1.0 - 2.0 * distance)

        chroma[pitch_class] += magnitude[i] * weight

    # ---- L2 normalize the chroma vector ----
    chroma_norm = np.linalg.norm(chroma)
    if chroma_norm == 0:
        return "Silence", 0.0
    chroma = chroma / chroma_norm

    # Sharpening: square and re-normalize
    chroma = chroma**2
    chroma_norm = np.linalg.norm(chroma)
    if chroma_norm == 0:
        return "Silence", 0.0
    chroma = chroma / chroma_norm

    # ---- Template matching ----
    best_score = -1.0
    best_root = 0
    best_chord_type = "maj"

    for root in range(12):
        # Roll chroma so candidate root is at index 0
        shifted_chroma = np.roll(chroma, -root)

        for chord_type, template in TEMPLATES.items():
            template = np.array(template, dtype=float)
            # L2 normalize the template
            template_norm = template / np.linalg.norm(template)

            # Cosine similarity (dot product of unit vectors)
            similarity = np.dot(shifted_chroma, template_norm)

            if similarity > best_score:
                best_score = similarity
                best_root = root
                best_chord_type = chord_type

    chord_name = get_chord_name(best_root, best_chord_type)
    return chord_name, best_score


# Quick self-test
if __name__ == "__main__":
    sr = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # C major: C4 + E4 + G4
    c = 0.5 * np.sin(2 * np.pi * 261.63 * t)
    e = 0.5 * np.sin(2 * np.pi * 329.63 * t)
    g = 0.5 * np.sin(2 * np.pi * 392.00 * t)
    chord_signal = c + e + g

    name, conf = detect_chord(chord_signal, sr)
    print(f"Detected: {name} with confidence {conf:.2f}")
