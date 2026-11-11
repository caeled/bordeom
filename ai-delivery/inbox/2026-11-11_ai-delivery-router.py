#!/usr/bin/env python3
"""
AI-Delivery Router -- a local web page for Steven Powell.

Pick files from any model's box (Inbox/<MODEL> or Outbox/<MODEL> under
C:\\Users\\ntadmin\\AI-Delivery) and copy them into any other box.

- Standard library only. No installs, no network beyond your own browser.
- Binds to 127.0.0.1 only: reachable from this machine, not from the LAN.
- COPIES only. It never moves, never deletes, and never overwrites a
  different file silently. If the destination already holds a file with
  the same name but different content, that file is reported as a
  conflict and skipped. Byte-identical files are reported as already
  there. Every copy is hash-verified and written to the destination
  box's transfer-log.txt.

Run:  python ai-delivery-router.py
Then open http://127.0.0.1:8765 in your browser.
Test: python ai-delivery-router.py --base <folder> --port 8766
"""

import argparse
import hashlib
import html
import os
import shutil
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_BASE = r"C:\Users\ntadmin\AI-Delivery"
SKIP_NAMES = {"transfer-log.txt", "readme-MUSE.md", "repo-url.txt"}
KINDS = ("Inbox", "Outbox")


# ---------------------------------------------------------------- boxes
def discover_boxes(base):
    boxes = []
    for kind in KINDS:
        kind_dir = os.path.join(base, kind)
        if not os.path.isdir(kind_dir):
            continue
        for name in sorted(os.listdir(kind_dir)):
            path = os.path.join(kind_dir, name)
            if os.path.isdir(path):
                boxes.append({"label": f"{kind}\\{name}", "kind": kind,
                              "model": name, "path": path})
    return boxes


def routable_files(box):
    out = []
    for name in os.listdir(box["path"]):
        full = os.path.join(box["path"], name)
        if os.path.isfile(full) and name.lower() not in SKIP_NAMES:
            st = os.stat(full)
            out.append({"name": name, "size": st.st_size,
                        "mtime": st.st_mtime})
    out.sort(key=lambda f: f["mtime"], reverse=True)
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- copy
def copy_one(src_box, dest_box, filename):
    """Returns (status, message). status in copied|identical|conflict|error."""
    if os.path.basename(filename) != filename or filename.lower() in SKIP_NAMES:
        return "error", f"{filename}: not a routable file name"
    src = os.path.join(src_box["path"], filename)
    dst = os.path.join(dest_box["path"], filename)
    if not os.path.isfile(src):
        return "error", f"{filename}: no longer in {src_box['label']}"
    if os.path.exists(dst):
        if os.path.getsize(dst) == os.path.getsize(src) and sha256(dst) == sha256(src):
            return "identical", f"{filename}: already in {dest_box['label']}, byte-identical"
        return "conflict", (f"{filename}: a DIFFERENT file with this name is already "
                            f"in {dest_box['label']} -- skipped, nothing overwritten")
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        return "error", f"{filename}: copy failed ({exc})"
    if sha256(dst) != sha256(src):
        return "error", f"{filename}: copy verification failed -- hashes differ"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {filename} routed {src_box['label']} -> {dest_box['label']} (web router)"
    with open(os.path.join(dest_box["path"], "transfer-log.txt"), "a", encoding="utf-8") as log:
        log.write(line + "\n")
    return "copied", f"{filename}: copied to {dest_box['label']}, verified, logged"


# ---------------------------------------------------------------- page
def fmt_size(n):
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


PAGE_CSS = """
body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1c2733;
       background: #f6f3ec; }
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: #5a6a78; margin-bottom: 18px; font-size: 13px; }
table.matrix { border-collapse: collapse; background: #fff;
               box-shadow: 0 1px 4px rgba(0,0,0,.12); }
table.matrix th, table.matrix td { border: 1px solid #d8d2c4; padding: 6px 10px;
               text-align: left; font-size: 13px; vertical-align: top; }
table.matrix th { background: #28455c; color: #fff; }
tr.src td { background: #f2f7ee; }
a.file { color: #1a4f7a; text-decoration: none; }
a.file:hover { text-decoration: underline; }
.srcradio { accent-color: #3d7a1e; width: 16px; height: 16px; }
.filecheck { accent-color: #28455c; width: 15px; height: 15px; }
select, button { font-size: 14px; padding: 6px 10px; }
button.go { background: #3d7a1e; color: #fff; border: 0; border-radius: 4px;
            padding: 10px 22px; font-size: 15px; cursor: pointer; }
button.go:hover { background: #356b19; }
.panel { background: #fff; border: 1px solid #d8d2c4; padding: 14px 18px;
         margin-top: 18px; max-width: 980px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.result li { margin: 3px 0; font-size: 14px; }
.copied { color: #2c5f14; } .identical { color: #5a6a78; }
.conflict { color: #a33b12; font-weight: 600; } .error { color: #a31212; font-weight: 600; }
.empty { color: #8a97a3; font-style: italic; }
.logbox { font-family: Consolas, monospace; font-size: 12px; white-space: pre-wrap;
          background: #fbfaf7; border: 1px solid #e3ddcf; padding: 10px; max-height: 220px;
          overflow-y: auto; }
"""


def render_page(base, boxes, results=None):
    esc = html.escape
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>",
             "<title>AI-Delivery Router</title>",
             f"<style>{PAGE_CSS}</style></head><body>",
             "<h1>AI-Delivery Router</h1>",
             f"<div class='sub'>Base: {esc(base)} &middot; Copies only &mdash; "
             "nothing is moved, deleted, or silently overwritten.</div>"]

    if results:
        parts.append("<div class='panel'><h2 style='margin-top:0'>Result</h2><ul class='result'>")
        for status, msg in results:
            parts.append(f"<li class='{esc(status)}'>{esc(msg)}</li>")
        parts.append("</ul></div>")

    parts.append("<form method='post' action='/copy'>")
    parts.append("<table class='matrix'><tr><th>From</th><th>Box</th><th>Files (click a name to read it)</th></tr>")
    for i, box in enumerate(boxes):
        files = routable_files(box)
        if files:
            links = "<br>".join(
                f"<label><input class='filecheck' type='checkbox' name='file' "
                f"value='{i}:{esc(f['name'], quote=True)}'> {esc(f['name'])}</label> "
                f"<a class='file' href='/file?box={i}&name={esc(f['name'], quote=True)}' target='_blank'>[read]</a> "
                f"<span class='empty'>{fmt_size(f['size'])} &middot; {fmt_time(f['mtime'])}</span>"
                for f in files)
        else:
            links = "<span class='empty'>no routable files</span>"
        parts.append(
            f"<tr><td><input class='srcradio' type='radio' name='src' value='{i}'></td>"
            f"<td><b>{esc(box['label'])}</b></td><td>{links}</td></tr>")
    parts.append("</table>")

    options = "".join(f"<option value='{i}'>{esc(b['label'])}</option>"
                      for i, b in enumerate(boxes))
    parts.append(
        "<div class='panel'><b>Copy the checked files into:</b> "
        f"<select name='dest'>{options}</select> "
        "<button class='go' type='submit'>Copy</button>"
        "<div class='sub' style='margin-top:8px'>How to use: choose the source box with a "
        "radio button on the left, tick the files in that row, pick the destination box, "
        "press Copy. A different file with the same name at the destination is never "
        "overwritten &mdash; it is reported as a conflict for you to settle in Explorer.</div></div>")
    parts.append("</form>")

    parts.append("<div class='panel'><h2 style='margin-top:0'>Recent routing activity</h2>")
    any_log = False
    for box in boxes:
        logpath = os.path.join(box["path"], "transfer-log.txt")
        if os.path.isfile(logpath):
            with open(logpath, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().strip().splitlines()
            if lines:
                any_log = True
                parts.append(f"<b>{esc(box['label'])}</b><div class='logbox'>"
                             + esc("\n".join(lines[-8:])) + "</div>")
    if not any_log:
        parts.append("<span class='empty'>no transfers logged yet</span>")
    parts.append("</div></body></html>")
    return "".join(parts)


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    base = DEFAULT_BASE

    def log_message(self, fmt, *args):  # quiet console
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        boxes = discover_boxes(self.base)
        if url.path == "/":
            self._send(200, render_page(self.base, boxes))
        elif url.path == "/file":
            q = parse_qs(url.query)
            try:
                box = boxes[int(q["box"][0])]
                name = q["name"][0]
            except (KeyError, ValueError, IndexError):
                self._send(400, "bad request")
                return
            if os.path.basename(name) != name:
                self._send(400, "bad file name")
                return
            full = os.path.join(box["path"], name)
            if not os.path.isfile(full):
                self._send(404, "not found")
                return
            ctype = "application/octet-stream"
            low = name.lower()
            if low.endswith(".txt") or low.endswith(".md"):
                ctype = "text/plain; charset=utf-8"
            elif low.endswith(".pdf"):
                ctype = "application/pdf"
            elif low.endswith((".jpg", ".jpeg")):
                ctype = "image/jpeg"
            elif low.endswith(".png"):
                ctype = "image/png"
            with open(full, "rb") as fh:
                self._send(200, fh.read(), ctype)
        else:
            self._send(404, "not found")

    def do_POST(self):
        if urlparse(self.path).path != "/copy":
            self._send(404, "not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        boxes = discover_boxes(self.base)
        results = []
        try:
            src_box = boxes[int(form["src"][0])]
            dest_box = boxes[int(form["dest"][0])]
        except (KeyError, ValueError, IndexError):
            self._send(200, render_page(self.base, boxes,
                                        [("error", "Pick a source box (radio button) and a destination box first.")]))
            return
        if src_box["path"] == dest_box["path"]:
            results.append(("error", "Source and destination are the same box. Nothing copied."))
        else:
            picked = []
            for value in form.get("file", []):
                idx, _, name = value.partition(":")
                if idx.isdigit() and int(idx) == boxes.index(src_box):
                    picked.append(name)
            if not picked:
                results.append(("error", "No files were checked in the source box's row. Nothing copied."))
            for name in picked:
                results.append(copy_one(src_box, dest_box, name))
        self._send(200, render_page(self.base, discover_boxes(self.base), results))


def main():
    ap = argparse.ArgumentParser(description="AI-Delivery Router (local web page)")
    ap.add_argument("--base", default=DEFAULT_BASE, help="AI-Delivery base folder")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default localhost only)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    if not os.path.isdir(args.base):
        print(f"Base folder not found: {args.base}")
        print("Create it, or point --base at the right folder.")
        sys.exit(1)
    Handler.base = args.base
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI-Delivery Router running at http://{args.host}:{args.port}")
    print(f"Base folder: {args.base}")
    print("Leave this window open while you use the page. Ctrl+C stops it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
