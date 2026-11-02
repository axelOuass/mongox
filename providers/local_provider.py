"""The MongoDB on this machine."""

from credentials import local_uri
from mongo_db import MongoDb
from providers.target import DOWN, UP, Target, port_open


class LocalTarget(Target):
    kind = "local"

    def __init__(self, host="127.0.0.1", port=27017):
        super().__init__("localhost", "%s:%s" % (host, port))
        self.host = host
        self.port = int(port)

    @property
    def address(self):
        return "%s:%d" % (self.host, self.port)

    def probe(self):
        self.status = UP if port_open(self.host, self.port) else DOWN
        if self.status == DOWN:
            self.note = "nothing listening"

    def open(self):
        return MongoDb(local_uri(self.host, self.port)), lambda: None
