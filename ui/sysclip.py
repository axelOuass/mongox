"""
Putting text on the system clipboard.

Knows about clipboard tools and nothing else. Four routes are tried in order:
the two Wayland and X11 command line tools, then OSC 52, an escape sequence
that asks the terminal emulator itself to set the clipboard. OSC 52 is the
only one that works over SSH, where the remote machine has no display of its
own, but terminals cap how much they accept through it.
"""

import base64
import os
import subprocess
from shutil import which

# Terminals commonly refuse OSC 52 payloads past a few tens of kilobytes.
OSC52_LIMIT = 64 * 1024

TOOLS = [
    ("wl-copy", ["wl-copy"]),
    ("xclip", ["xclip", "-selection", "clipboard"]),
    ("xsel", ["xsel", "--clipboard", "--input"]),
]


def copy(text):
    """Returns (status, detail).

    "tool"  - a clipboard program accepted it and the text is on the clipboard
    "osc52" - the escape sequence was written to the terminal, which may or
              may not have acted on it; there is no reply to read, so this
              cannot be confirmed
    "none"  - nothing was available
    """
    data = text.encode("utf-8")

    for name, command in TOOLS:
        if not which(command[0]):
            continue
        if name == "wl-copy" and not os.environ.get("WAYLAND_DISPLAY"):
            continue
        if name in ("xclip", "xsel") and not os.environ.get("DISPLAY"):
            continue
        try:
            process = subprocess.run(command, input=data, capture_output=True,
                                     timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, "%s failed: %s" % (name, error)
        if process.returncode == 0:
            return "tool", name
        return "none", "%s failed: %s" % (
            name, (process.stderr or b"").decode("utf-8", "replace")[:80])

    if len(data) <= OSC52_LIMIT and write_osc52(data):
        return "osc52", ""
    return "none", ""


def install_hint():
    """The package to suggest, based on which display server is running."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return "sudo apt install wl-clipboard"
    if os.environ.get("DISPLAY"):
        return "sudo apt install xclip"
    return "sudo apt install wl-clipboard      (or xclip on X11)"


def why_nothing(size_bytes):
    """Lines explaining the situation, for a machine with no clipboard tool."""
    lines = ["No clipboard program is installed, so mongox has no way to",
             "reach the system clipboard.", "",
             "  " + install_hint(), ""]
    if size_bytes > OSC52_LIMIT:
        lines += ["mongox can also ask the terminal itself to set the "
                  "clipboard,",
                  "but only for small amounts of text. This is %d KB, which is"
                  % (size_bytes // 1024),
                  "past what terminals accept."]
    else:
        lines += ["mongox asked the terminal itself to set the clipboard as a",
                  "fallback. Most terminals ignore that request, because it "
                  "lets",
                  "a remote machine overwrite your clipboard. If nothing "
                  "pasted,",
                  "that is why."]
    return lines


def write_osc52(data):
    """Ask the terminal to set its clipboard. Written to the terminal device
    rather than stdout, so it works while curses owns the screen."""
    sequence = b"\033]52;c;" + base64.b64encode(data) + b"\a"
    try:
        handle = os.open("/dev/tty", os.O_WRONLY)
    except OSError:
        return False
    try:
        os.write(handle, sequence)
        return True
    except OSError:
        return False
    finally:
        os.close(handle)


def available():
    """The tool that would be used, for display. None means OSC 52 only."""
    for name, command in TOOLS:
        if which(command[0]):
            return name
    return None
