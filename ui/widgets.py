"""
Reusable curses pieces. Nothing here knows what a database is: panes are fed
plain rows of text and hand back plain indices.

A row for ListPane is (label, note); note is right-aligned in the pane.
A row for TextPane is a list of (text, color slot, bold) spans.
"""

import curses

from ui.theme import (DANGER, DIM, FIELD, FRAME, FRAME_ON, ITEM, KEY, LITERAL,
                      NUMBER, OK, SEL, SEL_OFF, STRING, TITLE, attr)

TL, TR, BL, BR, HOR, VER = "┌", "┐", "└", "┘", "─", "│"
TICK = "✓"
MARK, TRACK, THUMB = "▌", "░", "█"


def put(window, y, x, text, style):
    """Write clipped text, swallowing the unavoidable bottom-right error."""
    height, width = window.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    try:
        window.addstr(y, x, text[:max(0, width - x - 1)], style)
    except curses.error:
        pass


class Panel:
    """A bordered box. Subclasses fill in the inside."""

    def __init__(self, title=""):
        self.title = title
        self.subtitle = ""
        self.active = False
        self.top = self.left = self.height = self.width = 0

    def place(self, top, left, height, width):
        self.top, self.left, self.height, self.width = top, left, height, width

    @property
    def inner_height(self):
        return max(0, self.height - 2)

    @property
    def inner_width(self):
        return max(0, self.width - 2)

    def draw_frame(self, window):
        style = attr(FRAME_ON, True) if self.active else attr(FRAME)
        put(window, self.top, self.left, TL + HOR * (self.width - 2) + TR, style)
        for row in range(1, self.height - 1):
            put(window, self.top + row, self.left, VER, style)
            put(window, self.top + row, self.left + self.width - 1, VER, style)
        put(window, self.top + self.height - 1, self.left,
            BL + HOR * (self.width - 2) + BR, style)

        if self.title:
            put(window, self.top, self.left + 2, " %s " % self.title.upper(),
                attr(TITLE, True) if self.active else attr(FRAME, True))
        if self.subtitle:
            text = " %s " % self.subtitle
            put(window, self.top + self.height - 1,
                self.left + self.width - len(text) - 3, text, attr(DIM))

    def draw_scrollbar(self, window, total, offset):
        if total <= self.inner_height or self.inner_height <= 0:
            return
        span = self.inner_height
        thumb_top = int(span * offset / total)
        thumb_len = max(1, int(span * span / total))
        style = attr(FRAME_ON) if self.active else attr(FRAME)
        for row in range(span):
            glyph = THUMB if thumb_top <= row < thumb_top + thumb_len else TRACK
            put(window, self.top + 1 + row, self.left + self.width - 1, glyph, style)


class ListPane(Panel):
    def __init__(self, title=""):
        super().__init__(title)
        self.rows = []
        self.index = 0
        self.offset = 0
        self.marked = set()

    def set_rows(self, rows, keep_index=False):
        self.rows = rows
        # Marks are row positions, and new rows renumber them, so they are
        # dropped whenever the contents change.
        self.marked = set()
        if not keep_index or self.index >= len(rows):
            self.index = 0
            self.offset = 0

    def toggle(self):
        if not self.rows:
            return
        if self.index in self.marked:
            self.marked.discard(self.index)
        else:
            self.marked.add(self.index)

    def clear_marks(self):
        self.marked = set()

    @property
    def selected(self):
        return self.index if self.rows else None

    def move(self, delta):
        if not self.rows:
            return False
        before = self.index
        target = self.index + delta
        if abs(delta) == 1:
            # One step past either end wraps to the other.
            target %= len(self.rows)
        else:
            target = max(0, min(len(self.rows) - 1, target))
        self.index = target
        return self.index != before

    def go(self, position):
        if not self.rows:
            return False
        before = self.index
        self.index = max(0, min(len(self.rows) - 1, position))
        return self.index != before

    def draw(self, window):
        self.draw_frame(window)
        span = self.inner_height
        if span <= 0:
            return

        if self.index < self.offset:
            self.offset = self.index
        elif self.index >= self.offset + span:
            self.offset = self.index - span + 1

        room = self.inner_width
        for row in range(span):
            y = self.top + 1 + row
            position = self.offset + row
            if position >= len(self.rows):
                put(window, y, self.left + 1, " " * room, attr(ITEM))
                continue

            label, note = self.rows[position]
            chosen = position == self.index
            style = (attr(SEL, True) if self.active else attr(SEL_OFF)) \
                if chosen else attr(ITEM)

            body = label[:max(0, room - len(note) - 2)] if note else label[:room]
            line = (TICK if position in self.marked else " ") + body
            line += " " * max(0, room - len(line) - len(note) - 1)
            if note:
                line += note + " "
            put(window, y, self.left + 1, line[:room], style)
            if chosen and self.active:
                put(window, y, self.left, MARK, attr(FRAME_ON, True))

        self.draw_scrollbar(window, len(self.rows), self.offset)


class TextPane(Panel):
    def __init__(self, title=""):
        super().__init__(title)
        self.rows = []
        self.offset = 0

    def set_rows(self, rows):
        self.rows = rows
        self.offset = 0

    def scroll(self, delta):
        limit = max(0, len(self.rows) - self.inner_height)
        self.offset = max(0, min(limit, self.offset + delta))

    def draw(self, window):
        self.draw_frame(window)
        span = self.inner_height
        if span <= 0:
            return
        self.offset = max(0, min(self.offset, max(0, len(self.rows) - span)))

        for row in range(span):
            y = self.top + 1 + row
            put(window, y, self.left + 1, " " * self.inner_width, attr(ITEM))
            if self.offset + row >= len(self.rows):
                continue
            x = self.left + 1
            for text, slot, bold in self.rows[self.offset + row]:
                if x - self.left >= self.width - 2:
                    break
                put(window, y, x, text, attr(slot, bold))
                x += len(text)

        self.draw_scrollbar(window, len(self.rows), self.offset)


class StatusBar:
    """The bottom line: either a message, or the key legend."""

    def __init__(self, keys):
        self.keys = keys
        self.message = ""
        self.slot = DIM

    def notify(self, text, slot=DIM):
        self.message, self.slot = text, slot

    def clear(self):
        self.message = ""

    def draw(self, window, y, width):
        put(window, y, 0, " " * (width - 1), attr(ITEM))
        if self.message:
            put(window, y, 1, self.message[:width - 2], attr(self.slot, True))
            return
        x = 1
        for key, label in self.keys:
            if x + len(key) + len(label) + 3 >= width:
                break
            put(window, y, x, key, attr(KEY, True))
            put(window, y, x + len(key), ":" + label + "  ", attr(DIM))
            x += len(key) + len(label) + 3


def _box(window, height, width, title, danger):
    screen_height, screen_width = window.getmaxyx()
    width = min(screen_width - 6, width)
    top = (screen_height - height) // 2
    left = (screen_width - width) // 2
    style = attr(DANGER, True) if danger else attr(FRAME_ON, True)

    put(window, top, left, TL + HOR * (width - 2) + TR, style)
    for row in range(1, height - 1):
        put(window, top + row, left, VER + " " * (width - 2) + VER, style)
    put(window, top + height - 1, left, BL + HOR * (width - 2) + BR, style)
    put(window, top, left + 2, " %s " % title, style)
    return top, left, width


def confirm(window, question, danger=False, body=None):
    """Yes or no. `body` adds detail lines above the question, for the cases
    where the answer depends on something the user has to read first."""
    body = body or []
    widest = max([len(line) for line in body] + [len(question)]) + 8
    height = 7 + (len(body) + 1 if body else 0)
    top, left, width = _box(window, height, max(46, widest), "CONFIRM", danger)

    for row, line in enumerate(body):
        put(window, top + 2 + row, left + 3, line[:width - 6], attr(DIM))

    question_row = top + height - 5
    put(window, question_row, left + 3, question[:width - 6],
        attr(DANGER, True) if danger else attr(ITEM, True))
    put(window, question_row + 2, left + 3, "y", attr(KEY, True))
    put(window, question_row + 2, left + 4, " yes", attr(DIM))
    put(window, question_row + 2, left + 11, "n", attr(KEY, True))
    put(window, question_row + 2, left + 12, " no", attr(DIM))
    window.refresh()

    while True:
        key = window.getch()
        if key in (ord("y"), ord("Y")):
            return True
        if key in (ord("n"), ord("N"), 27, ord("q")):
            return False


def prompt(window, label, initial=""):
    """A single-line text field. Returns the text, or None if cancelled."""
    top, left, width = _box(window, 7, 64, "INPUT", False)
    put(window, top + 2, left + 3, label[:width - 6], attr(ITEM, True))
    put(window, top + 5, left + 3, "enter", attr(KEY, True))
    put(window, top + 5, left + 8, " accept   ", attr(DIM))
    put(window, top + 5, left + 18, "esc", attr(KEY, True))
    put(window, top + 5, left + 21, " cancel", attr(DIM))

    field_width = width - 8
    text = initial
    # A prefilled value acts as selected text: the first key typed replaces it.
    fresh = bool(initial)
    curses.curs_set(1)
    try:
        while True:
            shown = text[-field_width:]
            put(window, top + 4, left + 3, shown.ljust(field_width), attr(STRING))
            window.move(top + 4, left + 3 + len(shown))
            window.refresh()

            key = window.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return text
            if key == 27:
                return None
            if key == 21:                       # ctrl-u, clear the line
                text, fresh = "", False
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                text, fresh = text[:-1], False
            elif 32 <= key < 127:
                if fresh:
                    text, fresh = "", False
                text += chr(key)
    finally:
        curses.curs_set(0)


def choose(window, title, options, index=0, hint=""):
    """A modal list. Returns the chosen index, or None if cancelled.

    Scrolls when the list is longer than the screen, so it copes with a
    collection that has fifty fields.
    """
    screen_height = window.getmaxyx()[0]
    visible = max(3, min(len(options), screen_height - 10))
    height = visible + 5 + (1 if hint else 0)
    widest = max([len(text) for text in options] + [len(title), len(hint), 30])
    top, left, width = _box(window, height, min(76, widest + 10), title, False)

    offset = 0
    while True:
        if index < offset:
            offset = index
        elif index >= offset + visible:
            offset = index - visible + 1

        for row in range(visible):
            position = offset + row
            y = top + 2 + row
            room = width - 6
            if position >= len(options):
                put(window, y, left + 3, " " * room, attr(ITEM))
                continue
            text = (" " + options[position])[:room].ljust(room)
            put(window, y, left + 3, text,
                attr(SEL, True) if position == index else attr(ITEM))
            put(window, y, left + 2, MARK if position == index else " ",
                attr(FRAME_ON, True))

        if len(options) > visible:
            put(window, top + 1, left + width - 12,
                "%d/%d" % (index + 1, len(options)), attr(DIM))
        if hint:
            put(window, top + height - 3, left + 3, hint[:width - 6], attr(DIM))
        put(window, top + height - 2, left + 3, "enter", attr(KEY, True))
        put(window, top + height - 2, left + 8, " choose   ", attr(DIM))
        put(window, top + height - 2, left + 18, "esc", attr(KEY, True))
        put(window, top + height - 2, left + 21, " cancel", attr(DIM))
        window.refresh()

        key = window.getch()
        if key in (curses.KEY_DOWN, ord("j")):
            index = (index + 1) % len(options)
        elif key in (curses.KEY_UP, ord("k")):
            index = (index - 1) % len(options)
        elif key == curses.KEY_NPAGE:
            index = min(len(options) - 1, index + visible)
        elif key == curses.KEY_PPAGE:
            index = max(0, index - visible)
        elif key in (10, 13, curses.KEY_ENTER):
            return index
        elif key in (27, ord("q")):
            return None


def message(window, title, body, danger=False):
    """A scrollable one-screen notice, for anything too long for the status bar."""
    lines = body.splitlines() or [""]
    height = min(window.getmaxyx()[0] - 4, len(lines) + 6)
    widest = max([len(line) for line in lines] + [len(title)]) + 8
    top, left, width = _box(window, height, widest, title, danger)
    for row, line in enumerate(lines[:height - 5]):
        put(window, top + 2 + row, left + 3, line[:width - 6], attr(ITEM))
    put(window, top + height - 2, left + 3, "any key", attr(KEY, True))
    put(window, top + height - 2, left + 10, " to continue", attr(DIM))
    window.refresh()
    # -1 is a read timeout and is skipped.
    while window.getch() == -1:
        pass


def tokenize_json(text):
    rows = []
    for line in text.splitlines():
        spans = []
        rest = line
        if '":' in rest:
            key, _, rest = rest.partition('":')
            spans.append((key + '"', FIELD, True))
            spans.append((":", DIM, False))
        while rest:
            stripped = rest.lstrip()
            pad = len(rest) - len(stripped)
            if pad:
                spans.append((" " * pad, DIM, False))
                rest = stripped
                continue
            if rest.startswith('"'):
                end = rest.find('"', 1)
                chunk = rest[:end + 1] if end > 0 else rest
                spans.append((chunk, STRING, False))
            elif rest[0].isdigit() or (rest[0] == "-" and rest[1:2].isdigit()):
                chunk = ""
                for char in rest:
                    if char.isdigit() or char in ".-+eE":
                        chunk += char
                    else:
                        break
                spans.append((chunk, NUMBER, True))
            elif rest[:4] in ("true", "null") or rest[:5] == "false":
                chunk = rest[:4] if rest[:4] in ("true", "null") else "false"
                spans.append((chunk, LITERAL, False))
            else:
                chunk = rest[0]
                spans.append((chunk, DIM, False))
            rest = rest[len(chunk):]
        rows.append(spans)
    return rows
