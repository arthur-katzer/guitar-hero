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

NOTE_KEYS = ["a", "s", "d", "f"]


class CursesUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.msg = ""
        self.stdscr.timeout(15)

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
