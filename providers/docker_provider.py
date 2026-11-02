"""
Finding MongoDB containers in Docker.

Containers are identified by image. Container names are set by the run script
and change. Matching is a substring test against known publishers, so
mongo:5.0, mongo:latest, bitnami/mongodb and percona/percona-server-mongodb
all match without a list of tags.
"""

import re
import subprocess
from shutil import which

from errors import MongoxError
from mongo_db import MongoDb
from providers.target import DOWN, UP, Target, port_open

# Substrings that mark an image as MongoDB. Lower-cased before comparison.
MONGO_IMAGES = ("mongo", "mongodb")

# Images that contain "mongo" but are not a server.
NOT_SERVERS = ("mongo-express", "mongoclient", "mongodb-exporter",
               "mongo-backup", "mongosh")

PORT_PATTERN = re.compile(r"(?:([\d.]+|\[[^\]]+\]):)?(\d+)->(\d+)/tcp")
DEFAULT_TIMEOUT = 4


class DockerUnavailable(Exception):
    """Docker is not installed, not running, or not usable by this user."""


class DockerProbe:
    """Finds MongoDB containers. Constructing it does no work."""

    def __init__(self, timeout=DEFAULT_TIMEOUT):
        self.timeout = timeout

    def installed(self):
        return which("docker") is not None

    def _run(self, arguments):
        try:
            result = subprocess.run(["docker"] + arguments,
                                    capture_output=True, text=True,
                                    timeout=self.timeout)
        except FileNotFoundError:
            raise DockerUnavailable("docker is not installed")
        except subprocess.TimeoutExpired:
            raise DockerUnavailable("docker did not respond")

        if result.returncode != 0:
            message = (result.stderr or "").strip().splitlines()
            first = message[0] if message else "docker failed"
            if "permission denied" in first.lower():
                raise DockerUnavailable("no permission to talk to docker")
            if "cannot connect" in first.lower() or "daemon" in first.lower():
                raise DockerUnavailable("docker daemon is not running")
            raise DockerUnavailable(first[:80])
        return result.stdout

    def containers(self):
        """Every running MongoDB container. Reads a tab-separated Go template,
        because --format json is missing on older Docker versions."""
        if not self.installed():
            raise DockerUnavailable("docker is not installed")

        output = self._run(["ps", "--format",
                            "{{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Ports}}"])
        found = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            container_id, image, name, ports = (part.strip() for part in parts[:4])
            if not is_mongo_image(image):
                continue
            host, port = published_address(ports)
            found.append(DockerTarget(container_id, image, name, host, port))
        return found


def is_mongo_image(image):
    """A MongoDB server image, and not one of the tools that ship alongside."""
    lowered = image.lower()
    if any(tool in lowered for tool in NOT_SERVERS):
        return False
    return any(marker in lowered for marker in MONGO_IMAGES)


def published_address(ports):
    """A reachable (host, port) from docker's Ports column, preferring the
    mapping to the container's own 27017. The column reads
    '127.0.0.1:27017->27017/tcp' when published and '27017/tcp' when not."""
    matches = PORT_PATTERN.findall(ports or "")
    if not matches:
        return None, None

    best = None
    for host, published, container in matches:
        host = (host or "127.0.0.1").strip("[]")
        if host == "0.0.0.0":
            host = "127.0.0.1"
        if container == "27017":
            return host, int(published)
        if best is None:
            best = (host, int(published))
    return best if best else (None, None)


class DockerTarget(Target):
    kind = "docker"

    def __init__(self, container_id, image, container_name, host, port):
        super().__init__(container_name or container_id[:12])
        self.container_id = container_id
        self.image = image
        self.container_name = container_name
        self.host = host
        self.port = port
        self.detail = "%s  %s" % (image, self.address or "not published")

    @property
    def address(self):
        return "%s:%d" % (self.host, self.port) if self.port else None

    @property
    def reachable(self):
        return self.port is not None

    def probe(self):
        if not self.reachable:
            self.status = DOWN
            self.note = "port not published to the host"
            return
        self.status = UP if port_open(self.host, self.port) else DOWN
        if self.status == DOWN:
            self.note = "published but not answering"

    def open(self):
        if not self.reachable:
            raise MongoxError(
                "container %s does not publish its port to the host.\n"
                "  Re-run it with -p 127.0.0.1:27017:27017, or connect from "
                "inside the container network." % self.name)
        source = MongoDb("mongodb://%s:%d/" % (self.host, self.port))
        source.label = "docker:%s" % self.name
        return source, lambda: None
