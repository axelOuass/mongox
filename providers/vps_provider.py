"""
.vps profiles and the SSH tunnel that makes them reachable.

A .vps file holds no secrets. It says where to find them: which local
credentials.env has the IP, and which file on the far side has the Mongo
password. The remote file is read over SSH at connect time and never written
to disk here.

Shape:

    {
      "name": "example",
      "host":  {"env": "~/path/credentials.env", "key": "IP_ADDRESS"},
      "ssh":   {"user": "root", "port": 22},
      "mongo": {"remote": "127.0.0.1:27017",
                "local_port": 27018,
                "env": "/root/mongodb/credentials.env",
                "user_key": "MONGO_ADMIN_USER",
                "password_key": "MONGO_ADMIN_PASSWORD",
                "auth_db": "admin"}
    }

"host" may instead be {"ip": "203.0.113.10"} if you would rather write it in.
Everything under "ssh" and "mongo" has a sensible default.
"""

import glob
import json
import os
import subprocess
import time

from credentials import (PASS_KEYS, USER_KEYS, build_uri, first_of,
                         parse_env_file, parse_env_text)
from errors import MongoxError
from mongo_db import MongoDb
from providers.target import UNKNOWN, UP, Target, port_open

SEARCH_DIRS = (".", "~/.config/mongox", "~/.mongox")
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
               "-o", "ConnectTimeout=8"]
TUNNEL_WAIT = 10.0


def find_profiles(extra_paths=()):
    """Every .vps file worth offering, nearest first, de-duplicated."""
    paths = []
    for path in extra_paths:
        paths.append(os.path.abspath(os.path.expanduser(path)))
    for directory in SEARCH_DIRS:
        expanded = os.path.abspath(os.path.expanduser(directory))
        paths.extend(sorted(glob.glob(os.path.join(expanded, "*.vps"))))

    seen, profiles = set(), []
    for path in paths:
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        profiles.append(VpsTarget(path))
    return profiles


class VpsTarget(Target):
    kind = "vps"

    def __init__(self, path):
        self.path = os.path.abspath(path)
        try:
            with open(self.path) as handle:
                self.profile = json.load(handle)
        except (OSError, ValueError) as error:
            raise MongoxError("%s is not readable JSON: %s" % (path, error))

        name = self.profile.get("name") or \
            os.path.splitext(os.path.basename(path))[0]
        super().__init__(name)
        self.tunnel = None
        self.detail = "%s@%s" % (self.ssh_user, self.host or "?")

    def _section(self, key):
        value = self.profile.get(key)
        return value if isinstance(value, dict) else {}

    @property
    def host(self):
        """The IP, written in the profile or read out of a local env file."""
        section = self._section("host")
        if section.get("ip"):
            return section["ip"]
        env_path = section.get("env")
        if not env_path:
            return None
        if not os.path.isabs(os.path.expanduser(env_path)):
            env_path = os.path.join(os.path.dirname(self.path), env_path)
        values = parse_env_file(os.path.expanduser(env_path))
        return values.get(section.get("key") or "IP_ADDRESS")

    @property
    def ssh_user(self):
        return self._section("ssh").get("user") or "root"

    @property
    def ssh_port(self):
        return int(self._section("ssh").get("port") or 22)

    @property
    def remote_address(self):
        remote = self._section("mongo").get("remote") or "127.0.0.1:27017"
        host, _, port = remote.partition(":")
        return host or "127.0.0.1", int(port or 27017)

    @property
    def local_port(self):
        """Not 27017, so a tunnel is not mistaken for a local Mongo."""
        return int(self._section("mongo").get("local_port") or 27018)

    def probe(self):
        """Not contacted. SSH can prompt for a passphrase, so the VPS is reached
        only once it is chosen."""
        self.status = UNKNOWN
        self.note = "" if self.host else "no IP in profile"

    def _ssh_base(self):
        return ["ssh"] + SSH_OPTIONS + ["-p", str(self.ssh_port),
                                        "%s@%s" % (self.ssh_user, self.host)]

    def read_remote_env(self):
        """Reads the remote credentials file over SSH, in memory."""
        path = self._section("mongo").get("env")
        if not path:
            return {}
        result = subprocess.run(self._ssh_base() + ["cat %s" % path],
                                capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            raise MongoxError("could not read %s on %s:\n  %s"
                              % (path, self.host,
                                 (result.stderr or "").strip()[:200]))
        return parse_env_text(result.stdout)

    def open_tunnel(self):
        """ssh -N -L localport:remote. Returns a closer."""
        if port_open("127.0.0.1", self.local_port, timeout=0.3):
            raise MongoxError(
                "local port %d is already in use.\n"
                "  Something is on it already - close it, or set a different "
                "local_port in %s" % (self.local_port, os.path.basename(self.path)))

        remote_host, remote_port = self.remote_address
        command = ["ssh"] + SSH_OPTIONS + [
            "-N", "-p", str(self.ssh_port),
            "-L", "%d:%s:%d" % (self.local_port, remote_host, remote_port),
            "%s@%s" % (self.ssh_user, self.host)]

        process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE)
        deadline = time.time() + TUNNEL_WAIT
        while time.time() < deadline:
            if process.poll() is not None:
                error = (process.stderr.read() or b"").decode("utf-8", "replace")
                raise MongoxError("ssh tunnel failed:\n  %s"
                                  % error.strip()[:300] or "ssh exited")
            if port_open("127.0.0.1", self.local_port, timeout=0.3):
                self.tunnel = process
                return lambda: self.close_tunnel(process)
            time.sleep(0.25)

        process.terminate()
        raise MongoxError("ssh tunnel did not come up within %.0fs" % TUNNEL_WAIT)

    def close_tunnel(self, process):
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self.tunnel = None

    def open(self):
        if not self.host:
            raise MongoxError("%s has no IP: set host.ip, or point host.env at a "
                              "file containing host.key"
                              % os.path.basename(self.path))

        values = self.read_remote_env()
        section = self._section("mongo")
        user = values.get(section.get("user_key", "")) or first_of(values, USER_KEYS)
        password = values.get(section.get("password_key", "")) or \
            first_of(values, PASS_KEYS)
        auth_db = section.get("auth_db") or values.get("MONGO_AUTH_DB")

        closer = self.open_tunnel()
        try:
            source = MongoDb(build_uri("127.0.0.1", self.local_port, user,
                                       password, auth_db))
        except Exception:
            closer()
            raise

        source.label = "vps:%s (%s)" % (self.name, self.host)
        self.status = UP
        return source, closer
