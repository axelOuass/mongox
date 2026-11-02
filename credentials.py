"""Mongo credentials from credentials.env files, and the URIs built from them."""

import os
from urllib.parse import quote_plus

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 27017
CRED_FILENAME = "credentials.env"

USER_KEYS = ("MONGO_USER", "MONGO_APP_USER", "MONGO_ADMIN_USER",
             "MONGO_INITDB_ROOT_USERNAME")
PASS_KEYS = ("MONGO_PASSWORD", "MONGO_APP_PASSWORD", "MONGO_ADMIN_PASSWORD",
             "MONGO_INITDB_ROOT_PASSWORD")


def parse_env_text(text):
    """KEY=VALUE lines. Skips comments, strips quotes and 'export'."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        value = value.split(" #")[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key.strip():
            values[key.strip()] = value
    return values


def parse_env_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return parse_env_text(handle.read())
    except OSError:
        return {}


def find_credentials():
    """Returns (values, path) of the nearest credentials.env above the cwd."""
    directory = os.getcwd()
    while True:
        candidate = os.path.join(directory, CRED_FILENAME)
        if os.path.isfile(candidate):
            return parse_env_file(candidate), candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return {}, None
        directory = parent


def first_of(values, keys):
    for key in keys:
        if values.get(key):
            return values[key]
    return None


def build_uri(host, port, user=None, password=None, auth_db=None):
    if not user:
        return "mongodb://%s:%s/" % (host, port)
    uri = "mongodb://%s:%s@%s:%s/" % (quote_plus(user), quote_plus(password or ""),
                                      host, port)
    if auth_db:
        uri += "?authSource=%s" % auth_db
    return uri


def local_uri(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """A local MongoDB usually has auth off, so credentials.env is optional."""
    values, _ = find_credentials()
    if values.get("MONGO_URI"):
        return values["MONGO_URI"]
    return build_uri(host, port, first_of(values, USER_KEYS),
                     first_of(values, PASS_KEYS), values.get("MONGO_AUTH_DB"))


def redact(uri):
    """The URI with its password hidden, for display."""
    if "@" not in uri:
        return uri
    scheme, _, rest = uri.partition("://")
    credential, _, host = rest.rpartition("@")
    return "%s://%s:***@%s" % (scheme, credential.split(":")[0], host)
