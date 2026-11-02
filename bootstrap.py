"""Installs pymongo at first run when mongox is started from source."""

import os
import subprocess
import sys

from errors import MongoxError


def ensure_pymongo():
    """A build from build.sh already contains pymongo and returns at once."""
    try:
        import pymongo  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get("MONGOX_BOOTSTRAPPED"):
        raise MongoxError("pymongo still not importable after install. "
                          "Try: pip install --user pymongo")

    sys.stderr.write("mongox needs the 'pymongo' package and it is not "
                     "installed.\n")
    if not sys.stdin.isatty():
        raise MongoxError("Not a terminal, refusing to install unattended. "
                          "Run: pip install --user pymongo")

    if not has_pip():
        raise MongoxError(
            "pip is not available for this Python.\n"
            "  Install it with:  sudo apt install --no-install-recommends "
            "python3-pip\n"
            "  Or build mongox with build.sh, which packs pymongo into the "
            "binary and needs nothing at run time.")

    if input("Install it now with 'pip install --user pymongo'? [y/N] "
             ).strip().lower() not in ("y", "yes"):
        raise MongoxError("Aborted. Install it with: pip install --user pymongo")

    code, output = run_pip(["--user", "pymongo"])

    # PEP 668: pip refuses to write into a system Python marked externally
    # managed. The override flag is asked for separately.
    if code != 0 and "externally-managed-environment" in output:
        sys.stderr.write(
            "\nThis system's Python is marked as externally managed, so pip "
            "will not\nwrite to it without --break-system-packages. That flag "
            "installs into a\ndirectory apt also manages.\n")
        if input("Retry with --break-system-packages? [y/N] "
                 ).strip().lower() in ("y", "yes"):
            code, output = run_pip(["--user", "--break-system-packages",
                                    "pymongo"])

    if code != 0:
        raise MongoxError("pip failed:\n%s" % output.strip()[-500:])

    # Re-exec so the installed package is on sys.path.
    os.environ["MONGOX_BOOTSTRAPPED"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


def has_pip():
    return subprocess.run([sys.executable, "-m", "pip", "--version"],
                          capture_output=True).returncode == 0


def run_pip(arguments):
    """Returns (exit code, output). The output is echoed, because it is the
    only progress shown during a download."""
    result = subprocess.run([sys.executable, "-m", "pip", "install"] + arguments,
                            capture_output=True, text=True)
    sys.stderr.write(result.stdout + result.stderr)
    return result.returncode, result.stdout + result.stderr
