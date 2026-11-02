"""
The first screen: which server. Shown before any database exists.

It knows there are targets with a kind, a name, a detail line and a status.
Discovery hands it a finished list.
"""

import curses

from ui import theme, widgets
from ui.theme import DANGER, DIM, FRAME, FRAME_ON, ITEM, KEY, OK, SEL, TITLE, attr
from ui.widgets import BL, BR, HOR, TL, TR, VER, put

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
DOT = {"up": ("●", OK), "down": ("●", DANGER),
       "checking": ("◌", DIM), "unknown": ("○", DIM)}
HEADINGS = {"local": "LOCAL", "docker": "DOCKER", "vps": "VPS"}
FRAME_WIDTH = 68


def run(discovery, auto=True, preselect=None):
    """Returns the chosen Target, or None if the user quit.

    With `auto`, a lone plain localhost is taken without asking. `preselect` is
    the key of the target to start on, so coming back from a connection lands
    on that connection rather than at the top of the list.
    """
    result = {}

    def loop(window):
        curses.curs_set(0)
        theme.init()
        window.keypad(True)
        window.timeout(80)
        result["target"] = Picker(discovery, auto, preselect).loop(window)

    curses.wrapper(loop)
    return result.get("target")


class Picker:
    def __init__(self, discovery, auto=True, preselect=None):
        self.discovery = discovery
        self.auto = auto
        self.preselect = preselect
        self.placed = False
        self.index = 0
        self.frame = 0
        self.message = ""
        self.geometry = None

    def build_rows(self):
        """A flat list of (target or None, kind) - None marks a heading.

        One target of a kind still gets its heading, so the screen reads the
        same whether there is one VPS or five.
        """
        rows, last_kind = [], None
        for target in self.discovery.targets:
            if target.kind != last_kind:
                rows.append((None, target.kind))
                last_kind = target.kind
            rows.append((target, target.kind))
        return rows

    def starting_index(self):
        """Where the cursor begins: the connection last used, if it is still
        in the list, otherwise the first thing that can be picked."""
        if self.preselect:
            for position, (target, _) in enumerate(self.rows):
                if target is not None and target.key == self.preselect:
                    return position
        return self.selectable[0]

    @property
    def selectable(self):
        return [index for index, (target, _) in enumerate(self.rows)
                if target is not None]

    def move(self, delta):
        positions = self.selectable
        if not positions:
            return
        if self.index not in positions:
            self.index = positions[0]
            return
        current = positions.index(self.index)
        # Wraps at both ends, as the panes in the browser do.
        self.index = positions[(current + delta) % len(positions)]

    def draw(self, window):
        # Discovery can resize the box, so a size change forces a full repaint.
        window.erase()
        height, width = window.getmaxyx()
        box_width = min(width - 4, FRAME_WIDTH)
        left = (width - box_width) // 2

        body = self.rows if self.discovery.done else []
        notes = self.discovery.notes() if self.discovery.done else []
        box_height = 7 if not self.discovery.done \
            else min(height - 2, len(body) + len(notes) + 5)
        top = max(0, (height - box_height) // 2)

        if (top, box_height, box_width) != self.geometry:
            self.geometry = (top, box_height, box_width)
            window.clearok(True)

        self.draw_frame(window, top, left, box_height, box_width)
        if not self.discovery.done:
            self.draw_spinner(window, top, left, box_height, box_width)
        else:
            self.draw_list(window, top, left, box_height, box_width, notes)
        window.refresh()

    def draw_frame(self, window, top, left, height, width):
        style = attr(FRAME_ON, True)
        put(window, top, left, TL + HOR * (width - 2) + TR, style)
        for row in range(1, height - 1):
            put(window, top + row, left, VER + " " * (width - 2) + VER, style)
        put(window, top + height - 1, left, BL + HOR * (width - 2) + BR, style)

        put(window, top, left + 2, " mongo", attr(OK, True))
        put(window, top, left + 8, "X ", attr(TITLE, True))
        label = " CONNECT "
        put(window, top, left + width - len(label) - 3, label, attr(DIM))

    def draw_spinner(self, window, top, left, height, width):
        glyph = SPINNER[self.frame % len(SPINNER)]
        middle = top + height // 2
        text = "%s  looking for servers" % glyph
        put(window, middle, left + (width - len(text)) // 2, text, attr(TITLE, True))
        hint = "localhost, docker, .vps profiles"
        put(window, middle + 1, left + (width - len(hint)) // 2, hint, attr(DIM))

    def draw_list(self, window, top, left, height, width, notes):
        y = top + 2
        for position, (target, kind) in enumerate(self.rows):
            if y >= top + height - 3:
                break
            if target is None:
                put(window, y, left + 3, HEADINGS.get(kind, kind.upper()),
                    attr(DIM, True))
                y += 1
                continue

            chosen = position == self.index
            glyph, slot = DOT.get(target.status, DOT["unknown"])
            room = width - 8

            # The detail shows what the target is, the dot whether it is up.
            # The note for the selected row goes in the footer.
            name = target.name[:22].ljust(22)
            here = target.key == self.preselect
            line = "%s%s %s" % ("·" if here else " ", name, target.detail)
            line = line[:room].ljust(room)

            put(window, y, left + 3, line,
                attr(SEL, True) if chosen else attr(ITEM))
            put(window, y, left + 2, "▌" if chosen else " ",
                attr(FRAME_ON, True))
            put(window, y, left + width - 4, glyph,
                attr(DANGER if target.status == "down" else slot, True))
            y += 1

        for note in notes:
            if y >= top + height - 3:
                break
            put(window, y + 1, left + 3, note[:width - 6], attr(DIM))
            y += 1

        footer = top + height - 2
        selected = self.rows[self.index][0] if self.rows else None
        if not self.message and selected is not None and selected.note:
            put(window, footer, left + 3, ("! " + selected.note)[:width - 6],
                attr(DANGER if selected.status == "down" else DIM, True))
            return
        if self.message:
            put(window, footer, left + 3, self.message[:width - 6],
                attr(DANGER, True))
            return
        x = left + 3
        for key, label in (("↑↓", "move"), ("enter", "connect"),
                           ("r", "rescan"), ("q", "quit")):
            put(window, footer, x, key, attr(KEY, True))
            put(window, footer, x + len(key), ":" + label + "  ", attr(DIM))
            x += len(key) + len(label) + 3

    def loop(self, window):
        self.rows = []
        while True:
            if self.discovery.done:
                self.rows = self.build_rows()
                if self.auto and self.discovery.only_plain_localhost:
                    return self.discovery.targets[0]
                if not self.placed and self.selectable:
                    self.index = self.starting_index()
                    self.placed = True

            self.draw(window)
            key = window.getch()
            if key == -1:
                self.frame += 1
                continue
            self.message = ""

            if key in (ord("q"), 27):
                return None
            if not self.discovery.done:
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                self.move(1)
            elif key in (curses.KEY_UP, ord("k")):
                self.move(-1)
            elif key in (10, 13, curses.KEY_ENTER, ord("l"), curses.KEY_RIGHT):
                target = self.rows[self.index][0] if self.rows else None
                if target is None:
                    continue
                if target.status == "down":
                    if not widgets.confirm(window,
                                           "%s looks down. Try anyway?" % target.name):
                        continue
                return target
            elif key == ord("r"):
                return "rescan"
