#!/usr/bin/env python3
"""
mongox - a MongoDB browser for the terminal.

    python3 mongox.py

Layout:
    mongox.py                start the picker, open what was chosen, browse
    connection_manager.py    the connection list and its probes
    providers/               localhost, Docker and .vps targets
    mongo_db.py              the live server, the only module using pymongo
    document_manager.py      edits and deletes
    clipboard_manager.py     copy and paste at three levels
    backup_manager.py        backup to and restore from .mongo files
    query_validator.py       searches into queries
    mongo_file_formatter.py  the .mongo file format
    document_formatter.py    labels, counts and sizes as text
    credentials.py           credentials.env files and URIs
    bootstrap.py             installs pymongo at first run
    ui/                      the curses interface
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bootstrap import ensure_pymongo
from clipboard_manager import Clipboard
from connection_manager import Discovery
from errors import MongoxError


def main():
    try:
        ensure_pymongo()
        clip = Clipboard()
        try:
            browse(clip)
        finally:
            clip.clear()          # the clipboard spools to a temp file
    except MongoxError as error:
        sys.exit("mongox: %s" % error)
    except KeyboardInterrupt:
        sys.exit(130)


def browse(clip):
    """Picker, then browser, then back to the picker when asked. They are
    separate curses sessions, so ssh can prompt for a passphrase in between."""
    from ui import browser, picker

    last = None
    first = True

    while True:
        discovery = Discovery()
        discovery.start()

        # Waits briefly for discovery. A lone localhost skips the picker, but
        # only at startup.
        deadline = time.time() + 0.4
        while not discovery.done and time.time() < deadline:
            time.sleep(0.05)

        if last:
            discovery.mark_used(last)

        if first and discovery.done and discovery.only_plain_localhost:
            target = discovery.targets[0]
        else:
            target = picker.run(discovery, auto=False, preselect=last)
        first = False

        if target is None:
            return
        if target == "rescan":
            continue

        sys.stdout.write("Connecting to %s ...\n" % target.name)
        sys.stdout.flush()
        try:
            source, closer = target.open()
        except MongoxError as error:
            sys.stderr.write("mongox: %s\n\n" % error)
            input("Press enter to go back to the connection list. ")
            continue

        last = target.key
        # A VPS opens read-only. w unlocks writes.
        read_only = target.kind == "vps"
        try:
            outcome = browser.run(source, read_only, clip)
        finally:
            closer()

        if outcome != browser.SWITCH:
            return


if __name__ == "__main__":
    main()
