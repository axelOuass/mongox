"""
The color scheme. Nothing else in ui/ names a color.

Values are xterm-256 indices.
"""

import curses

# semantic slots, used as curses color-pair ids
FRAME = 1        # inactive border
FRAME_ON = 2     # active border
TITLE = 3        # pane title, active
ITEM = 4         # normal row
SEL = 5          # selected row in the active pane
SEL_OFF = 6      # selected row in an inactive pane
DIM = 7          # counts, hints, punctuation
KEY = 8          # key names in the footer
STRING = 9       # JSON string values
FIELD = 10       # JSON keys
NUMBER = 11      # JSON numbers
LITERAL = 12     # JSON true/false/null
DANGER = 13
OK = 14

# the palette itself
_GREEN = 46
_GREEN_MID = 40
_GREEN_DARK = 22
_LIME = 118
_MINT = 121
_WHITE = 231
_GREY = 244
_RED = 196
_BLACK = 16

_SPEC = {
    FRAME: (_GREEN_DARK, -1),
    FRAME_ON: (_GREEN, -1),
    TITLE: (_LIME, -1),
    ITEM: (_GREEN_MID, -1),
    SEL: (_BLACK, _GREEN),
    SEL_OFF: (_GREEN, _GREEN_DARK),
    DIM: (_GREY, -1),
    KEY: (_MINT, -1),
    STRING: (_MINT, -1),
    FIELD: (_LIME, -1),
    NUMBER: (_WHITE, -1),
    LITERAL: (_GREY, -1),
    DANGER: (_RED, -1),
    OK: (_GREEN, -1),
}

# The second palette, used while a selection is being made. Same slots, so
# nothing that draws has to know which one is in force.
_ORANGE = 208
_ORANGE_MID = 172
_ORANGE_DARK = 94
_AMBER = 214
_PEACH = 222

_SELECT_SPEC = {
    FRAME: (_ORANGE_DARK, -1),
    FRAME_ON: (_ORANGE, -1),
    TITLE: (_AMBER, -1),
    ITEM: (_ORANGE_MID, -1),
    SEL: (_BLACK, _ORANGE),
    SEL_OFF: (_ORANGE, _ORANGE_DARK),
    DIM: (_GREY, -1),
    KEY: (_PEACH, -1),
    STRING: (_PEACH, -1),
    FIELD: (_AMBER, -1),
    NUMBER: (_WHITE, -1),
    LITERAL: (_GREY, -1),
    DANGER: (_RED, -1),
    OK: (_ORANGE, -1),
}

# fallback for a terminal without 256 colors
_BASIC = {_RED: curses.COLOR_RED, _WHITE: curses.COLOR_WHITE,
          _BLACK: curses.COLOR_BLACK, _GREY: curses.COLOR_WHITE}


def init(selecting=False):
    """Register every pair. Call once, after curses has started, and again
    whenever the palette changes: redefining a pair recolors everything
    already drawn with it at the next refresh."""
    curses.start_color()
    curses.use_default_colors()
    rich = curses.COLORS >= 256
    fallback = curses.COLOR_YELLOW if selecting else curses.COLOR_GREEN
    for slot, (foreground, background) in (
            _SELECT_SPEC if selecting else _SPEC).items():
        if not rich:
            foreground = _BASIC.get(foreground, fallback)
            background = _BASIC.get(background, background)
        curses.init_pair(slot, foreground, background)


def attr(slot, bold=False):
    value = curses.color_pair(slot)
    return value | curses.A_BOLD if bold else value
