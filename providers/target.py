"""
A Target is a server you could open: a name, a line of detail, and a status
that discovery fills in. open() returns (source, closer). The closer runs when
the browser exits and may do nothing.
"""

import socket

UNKNOWN, CHECKING, UP, DOWN = "unknown", "checking", "up", "down"


class Target:
    kind = "local"

    def __init__(self, name, detail=""):
        self.name = name
        self.detail = detail
        self.status = UNKNOWN
        self.note = ""

    @property
    def key(self):
        """Identifies a target across rescans, which rebuild the objects."""
        return (self.kind, self.name)

    def probe(self):
        """Cheap reachability check. Runs on a background thread."""
        self.status = UNKNOWN

    def open(self):
        """Returns (source, closer). May block and may raise MongoxError."""
        raise NotImplementedError


def port_open(host, port, timeout=0.6):
    """A TCP connect only, because it runs for every target at startup."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False
