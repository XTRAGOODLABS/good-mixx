"""Checks the problem-report log and link. Run: python3 tests/error_log_test.py"""
import json, os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))


def check_module(tmp):
    os.environ["GOODMIXX_ERROR_LOG"] = str(tmp / "errors.log")
    import error_log
    home = str(Path.home())
    error_log.record("page", "TypeError: boom at %s/Music/song.mp3 and /Users/someone/x" % home)
    text = (tmp / "errors.log").read_text()
    assert home not in text and "/Users/someone" not in text, text
    assert "~/Music/song.mp3" in text
    for i in range(260):
        error_log.record("helper", "problem %d %s" % (i, "x" * 80))
    assert len((tmp / "errors.log").read_text().strip().split("\n")) == 200
    url = urllib.parse.urlparse(error_log.report_url("1.8.1"))
    q = urllib.parse.parse_qs(url.query)
    assert url.netloc == "github.com" and url.path == "/XTRAGOODLABS/good-mixx/issues/new", url
    assert q["template"] == ["bug_report.yml"] and q["version"] == ["1.8.1"], q
    assert "problem 259" in q["error"][0] and "macOS" in q["mac"][0]
    assert len(error_log.report_url("1.8.1")) < 4000


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def check_server(tmp):
    port = _free_port()
    log = tmp / "server-errors.log"
    env = dict(os.environ, GOODMIXX_PORT=str(port), GOODMIXX_DATA=str(tmp / "data"), HOME=str(tmp / "home"),
               DJAY_LIBRARY=str(tmp / "none.db"), GOODMIXX_ERROR_LOG=str(log))
    proc = subprocess.Popen([sys.executable, "mixes_server.py"], cwd=ROOT / "app", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://localhost:%d" % port
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/info", timeout=2).read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            sys.exit("server did not start")
        req = urllib.request.Request(base + "/api/client-error", method="POST",
                                     data=json.dumps({"message": "ReferenceError: test from page"}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        assert "ReferenceError: test from page" in log.read_text()
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(base + "/api/report-problem", timeout=5)
            raise AssertionError("expected a redirect")
        except urllib.error.HTTPError as e:
            assert e.code == 302, e.code
            where = e.headers["Location"]
            assert where.startswith("https://github.com/XTRAGOODLABS/good-mixx/issues/new?"), where
            assert "test+from+page" in where or "test%20from%20page" in where, where
        page = urllib.request.urlopen(base + "/mixes", timeout=5).read().decode()
        assert 'href="/api/report-problem"' in page and "/api/client-error" in page
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    check_module(tmp)
    check_server(tmp)
    print("error log OK")
