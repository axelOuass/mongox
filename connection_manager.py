"""
Builds the list of connections and probes them in the background.

Finding and opening each kind of target is in providers/.
"""

import threading

from errors import MongoxError
from providers import docker_provider, vps_provider
from providers.local_provider import LocalTarget
from providers.target import CHECKING, UNKNOWN, UP


class Discovery:
    """Start it, draw a spinner while `done` is False, then read `targets`."""

    def __init__(self, local_host="127.0.0.1", local_port=27017, vps_paths=()):
        self.local = LocalTarget(local_host, local_port)
        self.vps_paths = tuple(vps_paths)
        self.targets = [self.local]
        self.docker_note = ""
        self.vps_note = ""
        self.done = False
        self._lock = threading.Lock()
        self._threads = []

    def start(self):
        self.local.status = CHECKING
        for worker in (self._find_local, self._find_docker, self._find_vps):
            thread = threading.Thread(target=self._guard, args=(worker,),
                                      daemon=True)
            thread.start()
            self._threads.append(thread)
        threading.Thread(target=self._await, daemon=True).start()

    def _guard(self, worker):
        try:
            worker()
        except Exception as error:
            with self._lock:
                self.docker_note = self.docker_note or str(error)[:80]

    def _await(self):
        for thread in self._threads:
            thread.join()
        self._collapse_duplicates()
        self.done = True

    def wait(self, timeout=None):
        for thread in self._threads:
            thread.join(timeout)
        self._collapse_duplicates()
        self.done = True
        return self.targets

    def _find_local(self):
        self.local.probe()

    def _find_docker(self):
        probe = docker_provider.DockerProbe()
        try:
            containers = probe.containers()
        except docker_provider.DockerUnavailable as error:
            with self._lock:
                self.docker_note = str(error)
            return
        for container in containers:
            container.status = CHECKING
            container.probe()
        with self._lock:
            self.targets.extend(containers)
        if not containers:
            self.docker_note = "no MongoDB containers running"

    def _find_vps(self):
        profiles = []
        for path in vps_provider.find_profiles(self.vps_paths):
            try:
                path.probe()
                profiles.append(path)
            except MongoxError as error:
                with self._lock:
                    self.vps_note = str(error)[:80]
        with self._lock:
            self.targets.extend(profiles)
        if not profiles and not self.vps_note:
            self.vps_note = "no .vps files found"

    def _collapse_duplicates(self):
        """A container published on the localhost address replaces the localhost
        entry, because the container names what is running."""
        with self._lock:
            occupied = {target.address for target in self.targets
                        if target.kind == "docker" and target.address}
            if self.local.address in occupied and len(self.targets) > 1:
                self.targets = [target for target in self.targets
                                if target is not self.local]
            self.targets.sort(key=lambda target:
                              ({"local": 0, "docker": 1, "vps": 2}[target.kind],
                               target.name))

    @property
    def only_plain_localhost(self):
        return (len(self.targets) == 1 and self.targets[0].kind == "local"
                and self.targets[0].status == "up")

    def notes(self):
        lines = []
        if self.docker_note:
            lines.append("docker: %s" % self.docker_note)
        if self.vps_note:
            lines.append("vps: %s" % self.vps_note)
        return lines

    def mark_used(self, key):
        """Shows the VPS just used as up. A VPS is never probed, because
        reaching one means SSH."""

        def apply():
            for target in self.targets:
                if target.key == key and target.status == UNKNOWN:
                    target.status = UP

        if self.done:
            apply()
            return
        threading.Thread(target=lambda: (self.wait(20), apply()),
                         daemon=True).start()
