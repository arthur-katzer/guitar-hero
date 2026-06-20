"""
minigame/runtime/engine.py
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
            if not self.events[self.current_index].get("_hit"):
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
        # Scan forward through all events in the hit window to find one
        # matching the pressed key (lanes are independent).
        for i in range(self.current_index, len(self.events)):
            ev = self.events[i]
            dt = ev["time"] - now
            if dt > self.hit_window:
                break  # past the window — no match
            if ev.get("_hit"):
                continue  # already hit — skip
            if abs(dt) <= self.hit_window and ev["key"].lower() == key.lower():
                ev["_hit"] = True
                self.score += self.base_points * self.multiplier
                self.combo += 1
                self.multiplier = 1 + self.combo // 10
                # Advance current_index past any leading hit events
                while (
                    self.current_index < len(self.events)
                    and self.events[self.current_index].get("_hit")
                ):
                    self.current_index += 1
                return True
        return False

    def update(self):
        self.current_event_index()
