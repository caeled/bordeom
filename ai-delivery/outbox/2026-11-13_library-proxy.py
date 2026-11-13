#!/usr/bin/env python3
"""
Everyday Cool Library App — home-server proxy for the web edition.

Why this exists: Project Gutenberg, the Internet Archive download nodes
and Standard Ebooks do not send the CORS header that lets a web page
fetch their book files, so the web edition of the library cannot read
those books in the page by itself. This tiny proxy runs on your own
server, fetches the file server-side (where CORS does not apply), and
hands it back with the header added. With it running, all six sources
read natively in the web edition.

Standard library only, like the rest of the app. Run it on the same
machine that hosts the web edition (the author's runs on PowellServer):

    python library-proxy.py            # port 8766
    python library-proxy.py 8770       # or pick a port

The web page looks for the proxy on its own host at port 8766
automatically. To point it somewhere else, set localStorage key
"ecl_proxy" to the base URL (for example "http://myserver:8766").

Safety: this is a fetch proxy, so it only fetches from the book
sources the library uses (an allowlist below), and it is meant for
your own home network. Do not expose it to the open internet.
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = 1
DEFAULT_PORT = 8766

# Only these hosts (and their subdomains) may be fetched through the
# proxy: the library's own book sources.
ALLOWED_HOSTS = (
    "gutenberg.org",
    "archive.org",
    "openlibrary.org",
    "standardebooks.org",
)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def host_allowed(host):
    host = (host or "").lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in ALLOWED_HOSTS)


class Handler(BaseHTTPRequestHandler):
    server_version = "LibraryProxy/1.0"

    # -- helpers ------------------------------------------------------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    # -- routes -------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/ping":
            self._json(200, {
                "ok": True,
                "service": "everyday-cool-library-proxy",
                "version": VERSION,
            })
            return
        if parsed.path == "/fetch":
            self._fetch(parsed)
            return
        self._json(404, {"ok": False, "error": "unknown path"})

    def _fetch(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        target = (qs.get("url") or [""])[0]
        if not target:
            self._json(400, {"ok": False, "error": "missing url parameter"})
            return
        t = urllib.parse.urlparse(target)
        if t.scheme not in ("http", "https") or not host_allowed(t.hostname):
            self._json(403, {
                "ok": False,
                "error": "host not on the library allowlist: %s" % (t.hostname or "?"),
            })
            return
        # Book file names can contain spaces and other characters urllib
        # refuses raw; quote them (keeping existing % escapes intact).
        target = urllib.parse.quote(target, safe=":/?#[]@!$&'()*+,;=%~")
        req = urllib.request.Request(target, headers={"User-Agent": BROWSER_UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(200)
                ctype = resp.headers.get("Content-Type") or "application/octet-stream"
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "public, max-age=86400")
                self._cors()
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as e:
            self._json(502, {"ok": False, "error": "source answered HTTP %d" % e.code})
        except Exception as e:  # network down, DNS, timeout...
            self._json(502, {"ok": False, "error": "fetch failed: %s" % e})

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] %s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Usage: python library-proxy.py [port]")
            return 1
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("Everyday Cool library proxy listening on port %d" % port)
    print("Web edition check: http://localhost:%d/ping" % port)
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
