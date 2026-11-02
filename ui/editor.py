"""Editing text in the user's own editor."""

import os
import subprocess
import tempfile
from shutil import which


def edit_text_externally(text):
    """Returns the edited text, or None when no editor is found."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        editor = next((name for name in ("nano", "vim", "vi") if which(name)), None)
    if not editor:
        return None

    handle = tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False)
    handle.write(text)
    handle.close()
    try:
        subprocess.call([editor, handle.name])
        with open(handle.name) as reopened:
            return reopened.read()
    finally:
        os.unlink(handle.name)
