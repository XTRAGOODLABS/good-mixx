"""DJ Mixes on its own - no stems page, no MIDI, nothing to install.
Run this on the Mac that is running djay, then open the address it prints on the iPad."""
import socket
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import mixes

PORT = 8766
mixes.STEMS = False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if mixes.handle_get(self):
            return
        if self.path.split("?")[0] in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/mixes")
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self):
        if not mixes.handle_post(self):
            self.send_error(404)

    def log_message(self, *args):
        pass


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def main():
    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    except OSError:
        print("DJ Mixes is already running on this Mac. You can close this window.")
        return 1
    name = socket.gethostname()
    if not name.endswith(".local"):
        name += ".local"
    ip = local_ip()
    now = mixes._now()
    print("")
    print("DJ MIXES IS RUNNING")
    print("")
    print("  On this Mac:   http://localhost:%d/mixes" % PORT)
    if ip:
        print("  On the iPad:   http://%s:%d/mixes" % (ip, PORT))
    print("  Or on the iPad: http://%s:%d/mixes" % (name, PORT))
    print("")
    print("  The iPad and this Mac need to be on the same Wi-Fi (a phone hotspot works).")
    print("  djay library: " + ("found" if now["djay"] else "NOT FOUND - " + now["error"]))
    print("")
    print("Keep this window open while you play. Close it to stop.")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
