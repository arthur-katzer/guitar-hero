"""
chord_templates.py
Defines chord patterns as chroma vectors (12 semitones, root = index 0)
Patterns represent the INTERVALS from the root, not absolute notes.
For example, a major chord has notes at root, 4 semitones up, and 7 semitones up.
"""

# Each template is a list of 12 numbers (0 or 1)
# The index is the semitone offset from the root
# 0=root, 1=minor second, 2=major second, 3=minor third, etc.

TEMPLATES = {
    # Triads
    "maj": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],  # major: root, major 3rd, perfect 5th
    "min": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],  # minor: root, minor 3rd, perfect 5th
    "dim": [
        1,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
    ],  # diminished: root, minor 3rd, diminished 5th
    "aug": [
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
    ],  # augmented: root, major 3rd, augmented 5th
    # Seventh chords (add these now — you'll want them for real music)
    "7": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0],  # dominant 7th: major triad + minor 7th
    "maj7": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],  # major 7th: major triad + major 7th
    "min7": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0],  # minor 7th: minor triad + minor 7th
    "dim7": [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0],  # diminished 7th: dim triad + dim 7th
    "m7b5": [
        1,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        1,
        0,
    ],  # half-diminished: dim triad + minor 7th
    # Suspended chords (common in rock/pop)
    "sus4": [1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0],  # root, perfect 4th, perfect 5th
    "sus2": [1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0],  # root, major 2nd, perfect 5th
    # Power chord (not really a chord in classical sense, but crucial for rock)
    "5": [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],  # root and perfect 5th only
}

# Map semitone numbers to note names (we'll use sharps, you can change to flats)
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def get_chord_name(root_semitone, chord_type):
    """
    Convert root (0-11) and chord type (key in TEMPLATES) to a readable name.
    Example: (0, "min") -> "C min"
    """
    root_name = NOTE_NAMES[root_semitone % 12]
    return f"{root_name} {chord_type}"
