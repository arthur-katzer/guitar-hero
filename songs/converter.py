#!/usr/bin/env python3
"""
songs/converter.py
Extracts note‑on events from all .mid files in songs/mid/ and writes
a rhythm‑game chart to songs/json/ (only if the json doesn't exist).
Each note is mapped to a keyboard key: the 8 most frequent notes
get assigned to a,s,d,f,j,k,l,;  (any other note → 'f' as fallback).
"""

import json
import os
import sys
from collections import Counter

import mido

# Home‑row keys for the 8 most common notes
NOTE_KEYS = list("asdf")
FALLBACK_KEY = "d"


def _build_tempo_map(track, ppq):
    """Build a list of (abs_tick, tempo) from a conductor/tempo track."""
    tempo_map = []
    abs_tick = 0
    for msg in track:
        abs_tick += msg.time
        if msg.type == "set_tempo":
            tempo_map.append((abs_tick, msg.tempo))
    if not tempo_map:
        tempo_map.append((0, 500000))  # default 120 BPM
    return tempo_map


def _ticks_to_seconds(abs_tick, tempo_map, ppq):
    """Convert an absolute tick position to seconds using the tempo map."""
    seconds = 0.0
    prev_tick = 0
    prev_tempo = 500000
    for map_tick, map_tempo in tempo_map:
        if map_tick >= abs_tick:
            break
        seconds += mido.tick2second(map_tick - prev_tick, ppq, prev_tempo)
        prev_tick = map_tick
        prev_tempo = map_tempo
    seconds += mido.tick2second(abs_tick - prev_tick, ppq, prev_tempo)
    return seconds


def extract_notes(mid_path):
    """Return a list of (time_in_seconds, midi_note_number)."""
    mid = mido.MidiFile(mid_path)
    ppq = mid.ticks_per_beat
    notes = []

    if mid.type == 1 and len(mid.tracks) > 1:
        # Type-1: tempo map lives in track 0, notes in remaining tracks.
        tempo_map = _build_tempo_map(mid.tracks[0], ppq)
        for track in mid.tracks[1:]:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    t = _ticks_to_seconds(abs_tick, tempo_map, ppq)
                    notes.append((round(t, 3), msg.note))
    else:
        # Type-0 or single-track: walk the merged stream.
        tempo = 500000
        abs_time = 0.0
        for msg in mid:
            if msg.type == "set_tempo":
                tempo = msg.tempo
            dt = mido.tick2second(msg.time, ppq, tempo)
            abs_time += dt
            if msg.type == "note_on" and msg.velocity > 0:
                notes.append((round(abs_time, 3), msg.note))

    notes.sort(key=lambda n: n[0])
    return notes


def build_key_mapping(notes):
    """Return a dict mapping MIDI note -> key letter for the most common notes."""
    note_counts = Counter(note for _, note in notes)
    most_common = [note for note, _ in note_counts.most_common(len(NOTE_KEYS))]
    mapping = {}
    for i, note in enumerate(most_common):
        mapping[note] = NOTE_KEYS[i]
    return mapping


def midi_to_note_name(midi_note):
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{note_names[midi_note % 12]}{midi_note // 12 - 1}"


def process_all():
    base_dir = os.path.dirname(__file__)
    mid_dir = os.path.join(base_dir, "mid")
    json_dir = os.path.join(base_dir, "json")
    os.makedirs(json_dir, exist_ok=True)

    converted = 0
    for fname in os.listdir(mid_dir):
        if not fname.endswith(".mid"):
            continue
        base = fname[:-4]
        json_path = os.path.join(json_dir, base + ".json")
        if os.path.exists(json_path):
            print(f"Skipping {fname} → already exists")
            continue

        mid_path = os.path.join(mid_dir, fname)
        notes = extract_notes(mid_path)
        if not notes:
            print(f"No notes found in {fname}")
            continue

        mapping = build_key_mapping(notes)

        events = []
        for t, note in sorted(notes):
            key = mapping.get(note, FALLBACK_KEY)
            events.append(
                {"time": t, "note": midi_to_note_name(note), "midi": note, "key": key}
            )

        chart = {"song": fname, "events": events}
        with open(json_path, "w") as f:
            json.dump(chart, f, indent=2)
        print(f"Created {base}.json ({len(events)} notes, {len(mapping)} unique keys)")
        converted += 1

    print(f"\nDone. {converted} new chart(s) written.")


if __name__ == "__main__":
    process_all()
