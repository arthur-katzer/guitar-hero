#!/usr/bin/env python3
"""Terminal rhythm minigame with keyboard lanes and a curses UI."""

import curses
import json
import os
import sys
import time

from minigame.runtime.engine import Engine
from minigame.runtime.interface import CursesUI

SONGS_JSON_DIR = "data/songs/json"
SONGS_MID_DIR = "data/songs/mid"


def load_chart(filename):
    with open(filename) as f:
        return json.load(f)


def list_available_songs():
    json_files = [f for f in os.listdir(SONGS_JSON_DIR) if f.endswith(".json")]
    return sorted(json_files)


def find_midi_for_chart(chart_name):
    base = os.path.splitext(chart_name)[0]
    mid_path = os.path.join(SONGS_MID_DIR, base + ".mid")
    return mid_path if os.path.exists(mid_path) else None


def choose_song():
    songs = list_available_songs()
    if not songs:
        print("No songs found in data/songs/json/. Run 'python -m minigame.cli.convert_songs' first.")
        sys.exit(1)
    print("Available songs:")
    for i, song in enumerate(songs):
        print(f"  {i + 1}. {os.path.splitext(song)[0]}")
    while True:
        try:
            choice = input("Select a song number (or 'q' to quit): ")
            if choice.lower() == "q":
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(songs):
                return songs[idx]
            else:
                print("Invalid choice.")
        except ValueError:
            print("Enter a number.")


def countdown(ui, seconds=3):
    for i in range(seconds, 0, -1):
        for _ in range(25):  # ~25 fps
            ui.show_message(f"Starting in {i}...")
            ui.draw_frame(Engine([]))  # dummy engine
            time.sleep(0.04)
    ui.show_message("Go!")


def game_loop(stdscr):
    # Song selection (terminal is still normal; we do this before curses init)
    # We need to do it before entering curses, so we call choose_song() outside,
    # then pass the file names in. That means main() will handle song selection,
    # then launch curses wrapper with those params.
    pass  # We'll restructure


def main():
    if len(sys.argv) >= 2:
        chart_file = sys.argv[1]
        midi_file = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Select song before entering curses (because curses messes with stdin)
        chart_name = choose_song()
        chart_file = os.path.join(SONGS_JSON_DIR, chart_name)
        midi_file = find_midi_for_chart(chart_name)

    chart = load_chart(chart_file)
    events = chart["events"]
    song_name = chart.get("song", os.path.basename(chart_file))

    # Start curses and run the game
    curses.wrapper(launch_game, chart_file, midi_file, events)


def launch_game(stdscr, chart_file, midi_file, events):
    engine = Engine(events)
    ui = CursesUI(stdscr)
    ui.setup()

    ui.show_message(f"Loaded: {chart_file} ({len(events)} notes)")
    ui.draw_frame(engine)
    time.sleep(0.5)

    # Countdown
    countdown(ui)

    if midi_file:
        engine.start_music(midi_file)

    engine.start_game(time.time())
    game_keys = set(e["key"] for e in events)

    # Main loop
    running = True
    while running:
        key = ui.get_keypress()
        if key is not None:
            if key == "q":
                running = False
                break
            if key in game_keys:
                if engine.try_hit(key):
                    ui.show_message("✅ Hit!")
                else:
                    ui.show_message("❌ Miss")
        engine.update()
        ui.draw_frame(engine)

    engine.stop_music()


if __name__ == "__main__":
    main()
