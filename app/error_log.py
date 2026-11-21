"""Problem reports for GOOD MIXX.

Errors are kept in a small log file on this Mac. Nothing is sent anywhere:
"Report a problem" only opens the GitHub form with the details filled in,
and the person decides whether to submit it."""
import os
import platform
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import urlencode

ISSUE_URL = "https://github.com/XTRAGOODLABS/good-mixx/issues/new"
MAX_LINES = 200      # lines kept in the log file
REPORT_LINES = 25    # most recent lines put into a report
REPORT_CHARS = 1800  # keeps the link short enough for browsers

_lock = threading.Lock()


def log_path():
    custom = os.environ.get("GOODMIXX_ERROR_LOG")
    if custom:
        return Path(custom)
    return Path.home() / "Library" / "Logs" / "GOOD MIXX errors.log"


def scrub(text):
    """Hide the person's user name in folder paths before anything is shown or shared."""
    text = str(text or "")
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    return re.sub(r"/Users/[^/\s]+", "/Users/~", text)


def _read():
    try:
        return [l for l in log_path().read_text(encoding="utf-8", errors="replace").split("\n") if l]
    except OSError:
        return []


def record(source, message):
    line = "%s [%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), source,
                           " ".join(scrub(message).split()))[:600]
    try:
        with _lock:
            path = log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = _read() + [line]
            path.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass   # logging must never break the app


def record_exception(source, exc):
    record(source, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-1500:])


def mac_description():
    chip = ""
    try:
        chip = subprocess.run(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
                              capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    version = platform.mac_ver()[0] or platform.release()
    return "%s, macOS %s" % (chip or platform.machine(), version)


def report_url(version=""):
    recent = "\n".join(_read()[-REPORT_LINES:])
    if len(recent) > REPORT_CHARS:
        recent = "…" + recent[-REPORT_CHARS:]
    params = {"template": "bug_report.yml", "version": version or "", "mac": mac_description(),
              "error": recent or "No errors were logged."}
    return ISSUE_URL + "?" + urlencode(params)


def idea_url():
    return ISSUE_URL + "?template=idea.yml"


def install():
    """Also log crashes, without changing how they are handled."""
    old_hook = sys.excepthook

    def hook(kind, exc, tb):
        if not issubclass(kind, KeyboardInterrupt):
            record("helper", "".join(traceback.format_exception(kind, exc, tb))[-1500:])
        old_hook(kind, exc, tb)
    sys.excepthook = hook

    old_thread_hook = threading.excepthook

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            record("helper", "".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                                args.exc_traceback))[-1500:])
        old_thread_hook(args)
    threading.excepthook = thread_hook
