"""Single instance for the layer-shell panels and daemons: $XDG_RUNTIME_DIR/<name>.pid, trusted only while
/proc/<pid>/cmdline still names <name>. Plus right_margin(): centre a top-right anchored panel under the pointer.
No GTK here, so daemons and `--bar` paths can import it cheaply.

  python3 -m fw13.panel test   self-check (no panel opened)
"""
import json
import os
import signal
import subprocess

from .hypr import hj

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")


def pidfile(name):
    return os.path.join(RUNTIME, f"{name}.pid")


def running(name):
    """The pid of a live <name> from its pidfile, or None (missing, garbage or stale pidfile)."""
    try:
        pid = int(open(pidfile(name)).read())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return pid if name.encode() in f.read() else None
    except (OSError, ValueError):
        return None


def close(name):
    """SIGTERM a running <name>; True if one was running (a second click on the icon closes the panel)."""
    pid = running(name)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def claim(name):
    with open(pidfile(name), "w") as f:
        f.write(str(os.getpid()))


def release(name):
    """Remove the pidfile if it is still ours."""
    try:
        if open(pidfile(name)).read() == str(os.getpid()):
            os.remove(pidfile(name))
    except OSError:
        pass


def right_margin(width):
    """Right margin that centres a panel of `width` under the pointer on the focused monitor, like fw-menu-anchor."""
    try:
        cx = json.loads(subprocess.run(["hyprctl", "-j", "cursorpos"], capture_output=True,
                                       text=True, timeout=3).stdout)["x"]
        m = next(m for m in hj("monitors") if m["focused"])
        return max(0, int(m["x"] + m["width"] / m["scale"] - cx - width / 2))
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, StopIteration):
        return 0


def selftest():
    import tempfile
    global RUNTIME
    saved, RUNTIME = RUNTIME, tempfile.mkdtemp()
    try:
        assert running("fw-nonexistent") is None and not close("fw-nonexistent")
        with open(pidfile("fw-stale"), "w") as f:
            f.write(str(os.getppid()))  # a live pid whose cmdline does not name fw-stale
        assert running("fw-stale") is None and not close("fw-stale")
        with open(pidfile("fw-junk"), "w") as f:
            f.write("not a pid")
        assert running("fw-junk") is None
        claim("python")  # our own cmdline contains "python"
        assert running("python") == os.getpid()
        release("python")
        assert not os.path.exists(pidfile("python"))
        with open(pidfile("fw-other"), "w") as f:
            f.write("1")
        release("fw-other")  # not ours: left alone
        assert os.path.exists(pidfile("fw-other"))
    finally:
        for n in os.listdir(RUNTIME):
            os.remove(os.path.join(RUNTIME, n))
        os.rmdir(RUNTIME)
        RUNTIME = saved
    print("panel: ok")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["test"]:
        selftest()
    else:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
