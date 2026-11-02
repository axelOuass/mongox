"""
Choosing a file to read, and a place to write one.

Built on widgets.choose. The `repaint` callable redraws what is underneath,
because listings differ in size and a larger box would show around a smaller one.
"""

import os

from ui import widgets

HOME = os.path.expanduser("~")


def listing(directory, suffix):
    """(directories, matching files), hidden entries left out."""
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return [], []

    directories, files = [], []
    for name in names:
        if name.startswith("."):
            continue
        full = os.path.join(directory, name)
        if os.path.isdir(full):
            directories.append(name)
        elif not suffix or name.endswith(suffix):
            files.append(name)
    return directories, files


def shorten(path, room=52):
    """~/long/path/... kept inside the box."""
    if path.startswith(HOME):
        path = "~" + path[len(HOME):]
    if len(path) <= room:
        return path
    return "..." + path[-(room - 3):]


def open_file(window, repaint, start=".", suffix=".mongo", title="OPEN"):
    """Walk the filesystem and return a chosen file, or None."""
    directory = os.path.abspath(os.path.expanduser(start))
    index = 0

    while True:
        directories, files = listing(directory, suffix)
        options = ["  .. up a level"]
        options += ["  %s/" % name for name in directories]
        options += ["  %s" % name for name in files]
        if not directories and not files:
            options.append("  (no %s files here)" % suffix)

        repaint()
        choice = widgets.choose(window, title, options,
                                index=min(index, len(options) - 1),
                                hint=shorten(directory))
        if choice is None:
            return None

        if choice == 0:
            parent = os.path.dirname(directory)
            directory, index = (parent if parent != directory else directory), 0
            continue

        position = choice - 1
        if position < len(directories):
            directory = os.path.join(directory, directories[position])
            index = 0
            continue

        position -= len(directories)
        if position < len(files):
            return os.path.join(directory, files[position])
        index = choice


def save_file(window, repaint, default_name, start=".", title="SAVE AS"):
    """Pick a directory and a name. Returns a full path, or None."""
    directory = os.path.abspath(os.path.expanduser(start))
    name = default_name

    while True:
        directories, _ = listing(directory, None)
        options = ["  save here as:  %s" % name,
                   "  change the name ...",
                   "  .. up a level"]
        options += ["  %s/" % entry for entry in directories]

        repaint()
        choice = widgets.choose(window, title, options, hint=shorten(directory))
        if choice is None:
            return None

        if choice == 0:
            return os.path.join(directory, name)
        if choice == 1:
            repaint()
            typed = widgets.prompt(window, "File name", name)
            if typed and typed.strip():
                name = typed.strip()
            continue
        if choice == 2:
            parent = os.path.dirname(directory)
            directory = parent if parent != directory else directory
            continue

        directory = os.path.join(directory, directories[choice - 3])
