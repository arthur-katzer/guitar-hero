# Guitar Hero Prototype — Fix Walkthrough

## Changes Made

### 1. `songs/converter.py` — Fixed type-1 MIDI timing (CRITICAL)

```diff:converter.py
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
NOTE_KEYS = list("asdfjkl;")
FALLBACK_KEY = "f"


def extract_notes(mid_path):
    """Return a list of (time_in_seconds, midi_note_number)."""
    mid = mido.MidiFile(mid_path)
    ppq = mid.ticks_per_beat
    tempo = 500000
    abs_time = 0.0
    notes = []

    for msg in mid:
        if msg.type == "set_tempo":
            tempo = msg.tempo
        dt = mido.tick2second(msg.time, ppq, tempo)
        abs_time += dt
        if msg.type == "note_on" and msg.velocity > 0:
            notes.append((round(abs_time, 3), msg.note))
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
===
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
NOTE_KEYS = list("asdfjkl;")
FALLBACK_KEY = "f"


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
```

The old `extract_notes()` used `for msg in mid` which merges all tracks in a type-1 MIDI. This collapsed timing from **119 seconds → 0.1 seconds** because note delta-ticks from track 1 were mixed into the global merged timeline without proper tempo resolution.

**Fix**: New helper functions `_build_tempo_map()` and `_ticks_to_seconds()` build a tempo map from track 0 (conductor), then iterate note tracks independently using absolute tick positions.

**Result**: Saint Seiya now spans 119s (≈2 min), 98137 spans 817s (≈13.6 min).

---

### 2. `game/interface.py` — Four UI/crash fixes

```diff:interface.py
"""
game/interface.py
Curses‑based terminal UI: moving note highway, score, hit zone.
"""

import curses

# Visual constants
BAR_WIDTH = 50
PAST_VISIBLE = 1.0  # seconds behind the NOW line
FUTURE_VISIBLE = 2.5  # seconds ahead of the NOW line
TOTAL_VISIBLE = PAST_VISIBLE + FUTURE_VISIBLE
HIT_WINDOW = 0.5  # must match engine

# Columns (0‑based)
NOW_COL = int(PAST_VISIBLE / TOTAL_VISIBLE * BAR_WIDTH)
HIT_ZONE_START = int((PAST_VISIBLE - HIT_WINDOW) / TOTAL_VISIBLE * BAR_WIDTH)
HIT_ZONE_END = int((PAST_VISIBLE + HIT_WINDOW) / TOTAL_VISIBLE * BAR_WIDTH)

NOTE_KEYS = ["a", "s", "d", "f", "j", "k", "l", ";"]


class CursesUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.msg = ""
        curses.curs_set(0)
        self.stdscr.nodelay(True)

    def get_keypress(self):
        key = self.stdscr.getch()
        if key == -1:
            return None
        if 32 <= key <= 126:
            return chr(key).lower()
        return None

    def draw_frame(self, engine):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        # ---------- top status ----------
        row = 0
        self.stdscr.addstr(row, 0, f"=== Rhythm Game ==="[: width - 1])
        row += 1
        self.stdscr.addstr(
            row,
            0,
            f"Score: {engine.score}  Misses: {engine.misses}  "
            f"Combo: {engine.combo}  x{engine.multiplier}"[: width - 1],
        )
        row += 1
        self.stdscr.addstr(row, 0, self.msg[: width - 1])
        row += 2  # blank line

        # ---------- note lanes ----------
        next_notes = engine.get_next_notes_for_keys(NOTE_KEYS, FUTURE_VISIBLE)
        now = engine.elapsed()

        for key in NOTE_KEYS:
            if row >= height - 2:
                break

            # Build list of (char, attr) for the bar
            bar = [(" ", curses.A_NORMAL)] * BAR_WIDTH

            # Hit zone background (white)
            for col in range(HIT_ZONE_START, HIT_ZONE_END + 1):
                if 0 <= col < BAR_WIDTH:
                    bar[col] = (" ", curses.A_REVERSE)

            # Red NOW marker
            if 0 <= NOW_COL < BAR_WIDTH:
                bar[NOW_COL] = ("|", curses.A_REVERSE | curses.A_BOLD)

            # Note marker
            t_until = next_notes.get(key)
            if t_until is not None and -PAST_VISIBLE <= t_until <= FUTURE_VISIBLE:
                col = int((t_until + PAST_VISIBLE) / TOTAL_VISIBLE * BAR_WIDTH)
                col = max(0, min(BAR_WIDTH - 1, col))
                bar[col] = ("#", curses.A_BOLD | curses.color_pair(1))

            # Draw the lane
            lane_str = f" {key} |"
            self.stdscr.addstr(row, 0, lane_str)
            x = len(lane_str)
            for i, (ch, attr) in enumerate(bar):
                if x + i >= width:
                    break
                self.stdscr.addstr(row, x + i, ch, attr)
            self.stdscr.addstr(row, x + len(bar), "|")
            row += 2

        # ---------- bottom ----------
        if row < height:
            self.stdscr.addstr(row, 0, "Press 'q' to quit."[: width - 1])
        self.stdscr.refresh()

    def show_message(self, msg):
        self.msg = msg

    def setup(self):
        curses.start_color()
        curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)
===
"""
game/interface.py
Curses‑based terminal UI: moving note highway, score, hit zone.
"""

import curses

# Visual constants
BAR_WIDTH = 50
PAST_VISIBLE = 1.0  # seconds behind the NOW line
FUTURE_VISIBLE = 2.5  # seconds ahead of the NOW line
TOTAL_VISIBLE = PAST_VISIBLE + FUTURE_VISIBLE
HIT_WINDOW = 0.5  # must match engine

# Columns (0‑based)
NOW_COL = int(PAST_VISIBLE / TOTAL_VISIBLE * BAR_WIDTH)
HIT_ZONE_START = int((PAST_VISIBLE - HIT_WINDOW) / TOTAL_VISIBLE * BAR_WIDTH)
HIT_ZONE_END = int((PAST_VISIBLE + HIT_WINDOW) / TOTAL_VISIBLE * BAR_WIDTH)

NOTE_KEYS = ["a", "s", "d", "f", "j", "k", "l", ";"]


class CursesUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.msg = ""
        self.stdscr.nodelay(True)

    def get_keypress(self):
        key = self.stdscr.getch()
        if key == -1:
            return None
        if 32 <= key <= 126:
            return chr(key).lower()
        return None

    def draw_frame(self, engine):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        # ---------- top status ----------
        row = 0
        self.stdscr.addstr(row, 0, "=== Rhythm Game ==="[: width - 1])
        row += 1
        status = (f"Score: {engine.score}  Misses: {engine.misses}  "
                  f"Combo: {engine.combo}  x{engine.multiplier}")
        self.stdscr.addstr(row, 0, status[: width - 1])
        row += 1
        self.stdscr.addstr(row, 0, self.msg[: width - 1])
        row += 2  # blank line

        # ---------- note lanes ----------
        all_notes = engine.get_all_visible_notes(
            NOTE_KEYS, FUTURE_VISIBLE, PAST_VISIBLE
        )

        for key in NOTE_KEYS:
            if row >= height - 2:
                break

            # Build list of (char, attr) for the bar
            bar = [(" ", curses.A_NORMAL)] * BAR_WIDTH

            # Hit zone background (white)
            for col in range(HIT_ZONE_START, HIT_ZONE_END + 1):
                if 0 <= col < BAR_WIDTH:
                    bar[col] = (" ", curses.A_REVERSE)

            # Red NOW marker
            if 0 <= NOW_COL < BAR_WIDTH:
                bar[NOW_COL] = ("|", curses.A_REVERSE | curses.A_BOLD)

            # Note markers — draw ALL visible notes in this lane
            for t_until in all_notes.get(key, []):
                col = int((t_until + PAST_VISIBLE) / TOTAL_VISIBLE * BAR_WIDTH)
                col = max(0, min(BAR_WIDTH - 1, col))
                bar[col] = ("#", curses.A_BOLD | curses.color_pair(1))

            # Draw the lane
            lane_str = f" {key} |"
            self.stdscr.addstr(row, 0, lane_str)
            x = len(lane_str)
            for i, (ch, attr) in enumerate(bar):
                if x + i >= width:
                    break
                self.stdscr.addstr(row, x + i, ch, attr)
            end_col = x + BAR_WIDTH
            if end_col < width:
                self.stdscr.addstr(row, end_col, "|")
            row += 2

        # ---------- bottom ----------
        if row < height:
            self.stdscr.addstr(row, 0, "Press 'q' to quit."[: width - 1])
        self.stdscr.refresh()

    def show_message(self, msg):
        self.msg = msg

    def setup(self):
        curses.start_color()
        curses.init_pair(1, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        try:
            curses.curs_set(0)
        except curses.error:
            pass  # terminal doesn't support cursor visibility control
```

| Bug | Fix |
|-----|-----|
| `curs_set(0)` before `start_color()` → crash | Moved into `setup()` after `start_color()`, wrapped in `try/except` |
| Score line `[: width-1]` sliced wrong substring | Wrapped combined f-string in parentheses |
| Only 1 note per lane visible | Switched to `get_all_visible_notes()`, loop renders all `#` markers |
| Closing `\|` pipe crashes on narrow terminals | Added `if end_col < width` guard |

---

### 3. `game/engine.py` — New `get_all_visible_notes()` method

```diff:engine.py
"""
game/engine.py
Core rhythm‑game logic: timing, scoring, combo, music playback.
"""

import subprocess
import time


class Engine:
    def __init__(self, events, hit_window=0.5):
        self.events = sorted(events, key=lambda e: e["time"])
        self.hit_window = hit_window
        self.current_index = 0
        self.score = 0
        self.misses = 0
        self.combo = 0
        self.multiplier = 1
        self.base_points = 100

        self.start_time = None
        self.midi_proc = None

    # ---------- music control ----------
    def start_music(self, midi_path, soundfont="/usr/share/soundfonts/FluidR3_GM.sf2"):
        cmd = ["fluidsynth", "-a", "pulseaudio", "-g", "2.0", soundfont, midi_path]
        self.midi_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(0.3)  # let synth warm up

    def stop_music(self):
        if self.midi_proc:
            self.midi_proc.terminate()
            self.midi_proc = None

    # ---------- game clock ----------
    def start_game(self, start_time):
        self.start_time = start_time

    def elapsed(self):
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    # ---------- event queue & scoring ----------
    def current_event_index(self):
        now = self.elapsed()
        while (
            self.current_index < len(self.events)
            and self.events[self.current_index]["time"] < now - self.hit_window
        ):
            self.misses += 1
            self.combo = 0
            self.current_index += 1
        return self.current_index

    def upcoming_events(self, count=3):
        self.current_event_index()
        return self.events[self.current_index : self.current_index + count]

    def get_next_notes_for_keys(self, keys, future_visible=3.0):
        """
        Return dict key -> time_until (seconds) for the next event of each key
        within future_visible.  None if no upcoming event.
        """
        self.current_event_index()
        now = self.elapsed()
        result = {key: None for key in keys}
        for ev in self.events[self.current_index :]:
            if ev["key"] in keys and result[ev["key"]] is None:
                if ev["time"] <= now + future_visible:
                    result[ev["key"]] = ev["time"] - now
            if all(v is not None for v in result.values()):
                break
        return result

    def try_hit(self, key):
        now = self.elapsed()
        self.current_event_index()
        if self.current_index >= len(self.events):
            return False
        ev = self.events[self.current_index]
        if (
            abs(now - ev["time"]) <= self.hit_window
            and ev["key"].lower() == key.lower()
        ):
            self.score += self.base_points * self.multiplier
            self.combo += 1
            self.multiplier = 1 + self.combo // 10
            self.current_index += 1
            return True
        return False

    def update(self):
        self.current_event_index()
===
"""
game/engine.py
Core rhythm‑game logic: timing, scoring, combo, music playback.
"""

import subprocess
import time


class Engine:
    def __init__(self, events, hit_window=0.5):
        self.events = sorted(events, key=lambda e: e["time"])
        self.hit_window = hit_window
        self.current_index = 0
        self.score = 0
        self.misses = 0
        self.combo = 0
        self.multiplier = 1
        self.base_points = 100

        self.start_time = None
        self.midi_proc = None

    # ---------- music control ----------
    def start_music(self, midi_path, soundfont="/usr/share/soundfonts/FluidR3_GM.sf2"):
        cmd = ["fluidsynth", "-a", "pulseaudio", "-g", "2.0", soundfont, midi_path]
        self.midi_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(0.3)  # let synth warm up

    def stop_music(self):
        if self.midi_proc:
            self.midi_proc.terminate()
            self.midi_proc = None

    # ---------- game clock ----------
    def start_game(self, start_time):
        self.start_time = start_time

    def elapsed(self):
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    # ---------- event queue & scoring ----------
    def current_event_index(self):
        now = self.elapsed()
        while (
            self.current_index < len(self.events)
            and self.events[self.current_index]["time"] < now - self.hit_window
        ):
            self.misses += 1
            self.combo = 0
            self.current_index += 1
        return self.current_index

    def upcoming_events(self, count=3):
        self.current_event_index()
        return self.events[self.current_index : self.current_index + count]

    def get_next_notes_for_keys(self, keys, future_visible=3.0):
        """
        Return dict key -> time_until (seconds) for the next event of each key
        within future_visible.  None if no upcoming event.
        """
        self.current_event_index()
        now = self.elapsed()
        result = {key: None for key in keys}
        for ev in self.events[self.current_index :]:
            if ev["key"] in keys and result[ev["key"]] is None:
                if ev["time"] <= now + future_visible:
                    result[ev["key"]] = ev["time"] - now
            if all(v is not None for v in result.values()):
                break
        return result

    def get_all_visible_notes(self, keys, future_visible=3.0, past_visible=1.0):
        """
        Return dict key -> list of time_until (seconds) for ALL events of each
        key within the visible window [-past_visible, +future_visible].
        """
        self.current_event_index()
        now = self.elapsed()
        result = {key: [] for key in keys}
        for ev in self.events[self.current_index :]:
            dt = ev["time"] - now
            if dt > future_visible:
                break
            if ev["key"] in result and -past_visible <= dt <= future_visible:
                result[ev["key"]].append(dt)
        return result

    def try_hit(self, key):
        now = self.elapsed()
        self.current_event_index()
        if self.current_index >= len(self.events):
            return False
        ev = self.events[self.current_index]
        if (
            abs(now - ev["time"]) <= self.hit_window
            and ev["key"].lower() == key.lower()
        ):
            self.score += self.base_points * self.multiplier
            self.combo += 1
            self.multiplier = 1 + self.combo // 10
            self.current_index += 1
            return True
        return False

    def update(self):
        self.current_event_index()
```

Returns `dict[str, list[float]]` — all `t_until` values for each key within the visible window, not just the first one.

---

## Verification

- **Chart JSON regenerated**: Both songs re-converted with correct timing
- **Frame rendering**: 60 frames drawn without crash
- **Full game loop**: 194 frames in 3s (65 fps), notes scrolling, misses counting, score/combo working
- No `curses.error` exceptions on startup
