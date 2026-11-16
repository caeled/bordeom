#!/usr/bin/env python3
"""
Library App - a simple personal library for Windows.

Search Project Gutenberg and Wikibooks, download EPUBs, read them in a
plain reader, and pick up right where you left off. Your place is saved
automatically for every book.

No third-party packages: Python standard library only.
Data lives next to this script in a "LibraryData" folder:
    LibraryData/Books/      downloaded EPUB files
    LibraryData/library.json  your downloaded books
    LibraryData/places.json   reading position per book

Run:  python LibraryApp.py        (or double-click LibraryApp.bat)
Self-test (no window):  python LibraryApp.py --selftest
"""

import html
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
import zlib
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

APP_NAME = "Everyday Cool Library App"
USER_AGENT = "LibraryApp/1.0 (personal reader; contact: caeled@gmail.com)"

import sys

if getattr(sys, "frozen", False):
    # Running as a PyInstaller exe: keep LibraryData next to the exe,
    # not inside the bundle's internals.
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "LibraryData")
BOOKS_DIR = os.path.join(DATA_DIR, "Books")
LIBRARY_JSON = os.path.join(DATA_DIR, "library.json")
PLACES_JSON = os.path.join(DATA_DIR, "places.json")

GUTENDEX = "https://gutendex.com/books/"
WIKIBOOKS_API = "https://en.wikibooks.org/w/api.php"
WIKISOURCE_API = "https://en.wikisource.org/w/api.php"
WSEXPORT = "https://ws-export.wmcloud.org/"
IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_METADATA = "https://archive.org/metadata/"
IA_DOWNLOAD = "https://archive.org/download/"
OL_SEARCH = "https://openlibrary.org/search.json"
SE_BASE = "https://standardebooks.org"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def resource_candidates(name):
    """Every place a file that ships with the app (banner, icon) may sit:
    the PyInstaller bundle (sys._MEIPASS: the _internal folder in a
    one-folder build, a temp folder in a one-file build), next to the
    exe or script, and an _internal folder next to the exe."""
    places = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        places.append(bundle)
    places.append(BASE_DIR)
    places.append(os.path.join(BASE_DIR, "_internal"))
    places.append(os.path.dirname(os.path.abspath(__file__)))
    seen, out = set(), []
    for d in places:
        c = os.path.join(d, name)
        key = os.path.normcase(os.path.abspath(c))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def resource_path(name):
    """Path of a file that ships with the app; the first candidate that
    exists, else the first candidate (so callers get a sensible path to
    report)."""
    cands = resource_candidates(name)
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


def log_problem(msg):
    """Append a line to LibraryData/app.log. Used for things the app
    shrugs off (missing banner, icon) so a windowed exe, which has no
    console, still leaves a trace of why."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "app.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.rstrip() + "\n")
    except Exception:
        pass


def ensure_dirs():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def http_get(url, timeout=60, headers=None):
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    last_err = None
    for _attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.headers.get_content_type()
        except Exception as e:  # one retry: some hosts are slow to answer
            last_err = e
    raise last_err


def http_get_json(url, timeout=60):
    raw, _ = http_get(url, timeout=timeout)
    return json.loads(raw.decode("utf-8", "replace"))


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def slugify(text, fallback="book"):
    s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return s[:60] or fallback


# --------------------------------------------------------------------------
# search: Project Gutenberg (Gutendex) and Wikibooks (MediaWiki API)
# --------------------------------------------------------------------------

def search_gutenberg(query, limit=20):
    url = GUTENDEX + "?" + urllib.parse.urlencode({"search": query})
    data = http_get_json(url)
    out = []
    for b in data.get("results", [])[:limit]:
        formats = b.get("formats", {}) or {}
        epub_url = (
            formats.get("application/epub+zip")
            or formats.get("application/epub")
        )
        authors = ", ".join(
            a.get("name", "") for a in b.get("authors", []) if a.get("name")
        )
        out.append(
            {
                "source": "gutenberg",
                "id": "gutenberg-%s" % b.get("id"),
                "title": b.get("title", "Untitled"),
                "author": authors,
                "epub_url": epub_url,
                "downloads": b.get("download_count"),
            }
        )
    return out


def _search_wiki(api, source, label, query, limit=20):
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 0,
        "srlimit": limit,
        "format": "json",
    }
    url = api + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    out = []
    seen_books = set()
    for hit in data.get("query", {}).get("search", []):
        title = hit.get("title", "")
        # A wiki "book" is its root page; chapters live under Title/...
        root = title.split("/")[0].strip()
        if not root or root in seen_books:
            continue
        seen_books.add(root)
        out.append(
            {
                "source": source,
                "id": "%s-%s" % (source, slugify(root)),
                "title": root,
                "author": label,
                "epub_url": None,  # built/downloaded at fetch time
                "book_title": root,
            }
        )
    return out


def search_wikibooks(query, limit=20):
    return _search_wiki(WIKIBOOKS_API, "wikibooks", "Wikibooks contributors", query, limit)


def search_wikisource(query, limit=20):
    return _search_wiki(WIKISOURCE_API, "wikisource", "Wikisource", query, limit)


# --------------------------------------------------------------------------
# Internet Archive + Open Library: the same stock, different catalogs.
# Most IA books are lending copies with a locked file; only items with
# an unrestricted, plain EPUB or PDF file can be downloaded here.
# --------------------------------------------------------------------------

def ia_open_file(identifier):
    """Metadata check for one archive.org item. Returns
    {'filename': ..., 'ext': '.epub'|'.pdf', 'url': ...} or None."""
    meta = http_get_json(IA_METADATA + identifier, timeout=30)
    md = meta.get("metadata") or {}
    if str(md.get("access-restricted-item", "")).lower() in ("true", "1"):
        return None
    files = meta.get("files") or []
    epubs = [
        f["name"] for f in files
        if f.get("name", "").lower().endswith(".epub")
        and "_lcp" not in f["name"] and "encrypted" not in f["name"]
    ]
    if epubs:
        name = epubs[0]
        return {"filename": name, "ext": ".epub",
                "url": IA_DOWNLOAD + identifier + "/" + urllib.parse.quote(name)}
    pdfs = [f["name"] for f in files if f.get("name", "").lower().endswith(".pdf")]
    preferred = [n for n in pdfs if n.lower().endswith("_text.pdf")] or pdfs
    if preferred:
        name = preferred[0]
        return {"filename": name, "ext": ".pdf",
                "url": IA_DOWNLOAD + identifier + "/" + urllib.parse.quote(name)}
    return None


def _ia_result(identifier, title, author):
    try:
        f = ia_open_file(identifier)
    except Exception:
        return None
    if not f:
        return None
    return {
        "source": "archive",
        "id": "ia-" + slugify(identifier),
        "title": title or identifier,
        "author": author,
        "file_url": f["url"],
        "ext": f["ext"],
    }


def search_internet_archive(query, limit=12, probe=18):
    q = "mediatype:texts AND (title:(%s) OR creator:(%s))" % (query, query)
    params = {
        "q": q,
        "fl[]": ["identifier", "title", "creator"],
        "sort[]": ["downloads desc"],
        "rows": probe,
        "output": "json",
    }
    url = IA_SEARCH + "?" + urllib.parse.urlencode(params, doseq=True)
    data = http_get_json(url, timeout=30)
    out = []
    for doc in (data.get("response") or {}).get("docs", []):
        ident = doc.get("identifier")
        if not ident:
            continue
        creator = doc.get("creator")
        if isinstance(creator, list):
            creator = ", ".join(creator)
        item = _ia_result(ident, doc.get("title", ""), creator or "")
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def search_open_library(query, limit=12, probe=20):
    params = {
        "q": query,
        "fields": "title,author_name,ia",
        "limit": probe,
    }
    url = OL_SEARCH + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url, timeout=30)
    out = []
    seen = set()
    for doc in data.get("docs", []):
        for ident in doc.get("ia") or []:
            if ident in seen:
                continue
            seen.add(ident)
            try:
                f = ia_open_file(ident)
            except Exception:
                f = None
            if not f:
                continue
            authors = ", ".join(doc.get("author_name") or [])
            out.append(
                {
                    "source": "openlibrary",
                    "id": "ol-" + slugify(ident),
                    "title": doc.get("title", ident),
                    "author": authors,
                    "file_url": f["url"],
                    "ext": f["ext"],
                }
            )
            break
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------
# Standard Ebooks: the OPDS feeds are Patrons Circle only, but the
# public website search and per-book download links are open.
# --------------------------------------------------------------------------

def search_standard_ebooks(query, limit=10):
    url = SE_BASE + "/ebooks?" + urllib.parse.urlencode({"query": query})
    raw, _ = http_get(url, timeout=60, headers={"User-Agent": BROWSER_UA})
    page = raw.decode("utf-8", "replace")
    seen, out = set(), []
    for author_slug, title_slug in re.findall(
        r'href="/ebooks/([A-Za-z0-9-]+)/([A-Za-z0-9-]+)"', page
    ):
        key = (author_slug, title_slug)
        if key in seen:
            continue
        seen.add(key)
        book_url = "%s/ebooks/%s/%s" % (SE_BASE, author_slug, title_slug)
        try:
            brow, _ = http_get(book_url, timeout=30, headers={"User-Agent": BROWSER_UA})
            bpage = brow.decode("utf-8", "replace")
        except Exception:
            continue
        epub = None
        for cand in re.findall(r'href="(/ebooks/[^"]*?\.epub)"', bpage):
            if ".kepub.epub" in cand or "_advanced.epub" in cand:
                continue
            epub = SE_BASE + cand
            break
        if not epub:
            continue
        title = title_slug.replace("-", " ").title()
        author = author_slug.replace("-", " ").title()
        out.append(
            {
                "source": "standardebooks",
                "id": "se-" + slugify(title_slug),
                "title": title,
                "author": author,
                "file_url": epub + "?source=download",
                "ext": ".epub",
            }
        )
        if len(out) >= limit:
            break
    return out


def download_direct(item, dest_path):
    """Download a result that has a direct file URL (Archive, Open
    Library, Standard Ebooks)."""
    raw, _ = http_get(item["file_url"], timeout=180)
    ext = item.get("ext") or ".epub"
    if ext == ".epub" and raw[:2] != b"PK":
        raise ValueError("The download did not return an EPUB file.")
    if ext == ".pdf" and raw[:4] != b"%PDF":
        raise ValueError("The download did not return a PDF file.")
    with open(dest_path, "wb") as f:
        f.write(raw)
    return dest_path


# --------------------------------------------------------------------------
# EPUB download / build
# --------------------------------------------------------------------------

def download_gutenberg_epub(item, dest_path):
    url = item.get("epub_url")
    if not url:
        gid = str(item["id"]).rsplit("-", 1)[-1]
        url = "https://www.gutenberg.org/cache/epub/%s/pg%s.epub" % (gid, gid)
    raw, _ = http_get(url, timeout=120)
    if not raw[:2] == b"PK":
        raise ValueError("Gutenberg did not return an EPUB file.")
    with open(dest_path, "wb") as f:
        f.write(raw)
    return dest_path


def fetch_wiki_epub(item, dest_path, api, source_name):
    """Try the Wikimedia export tool first; fall back to assembling an
    EPUB from the book's pages through the API. If the export comes
    back thin (index pages export almost nothing), keep whichever
    version has more actual text."""
    title = item["book_title"]
    params = {"format": "epub", "lang": "en", "page": title}
    url = WSEXPORT + "?" + urllib.parse.urlencode(params)
    exported = False
    try:
        raw, _ = http_get(url, timeout=150)
        if raw[:2] == b"PK":
            with open(dest_path, "wb") as f:
                f.write(raw)
            exported = True
    except Exception:
        pass
    if exported:
        def _chars(path):
            try:
                return sum(len(c["text"]) for c in read_epub_chapters(path))
            except Exception:
                return 0

        if _chars(dest_path) >= 8000:
            return dest_path
        alt = dest_path + ".alt"
        try:
            build_wikibooks_epub(title, alt, api=api, source_name=source_name)
            if _chars(alt) > _chars(dest_path):
                os.replace(alt, dest_path)
            else:
                os.remove(alt)
        except Exception:
            try:
                os.remove(alt)
            except Exception:
                pass
        return dest_path
    return build_wikibooks_epub(title, dest_path, api=api, source_name=source_name)


def fetch_wikibooks_epub(item, dest_path):
    return fetch_wiki_epub(item, dest_path, WIKIBOOKS_API, "Wikibooks contributors")


def fetch_wikisource_epub(item, dest_path):
    return fetch_wiki_epub(item, dest_path, WIKISOURCE_API, "Wikisource")


class _TextExtract(HTMLParser):
    """Pull readable text out of an XHTML/HTML chunk."""

    BLOCK = {
        "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "section", "article",
    }
    SKIP = {"script", "style", "sup"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title = None
        self._skip_depth = 0
        self._in_title = False
        self._title_parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        if tag in ("h1", "h2"):
            self._in_title = True
            self._title_parts = []
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag in ("h1", "h2") and self._in_title:
            self._in_title = False
            text = " ".join(" ".join(self._title_parts).split())
            if text and not self.title:
                self.title = text
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        out, blank = [], False
        for line in lines:
            if line:
                out.append(line)
                blank = False
            elif not blank:
                out.append("")
                blank = True
        return "\n".join(out).strip()


def _wikibooks_page_html(title, api=WIKIBOOKS_API):
    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "disableeditsection": 1,
    }
    url = api + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    parse = data.get("parse") or {}
    text = (parse.get("text") or {}).get("*", "")
    return text


def _wikibooks_book_pages(book_title, api=WIKIBOOKS_API):
    """Main page plus its subpages, in the order the main page links them."""
    params = {
        "action": "parse",
        "page": book_title,
        "prop": "links",
        "format": "json",
    }
    url = api + "?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url)
        links = (data.get("parse") or {}).get("links", [])
    except Exception:
        links = []
    pages = [book_title]
    prefix = book_title.rstrip("/") + "/"
    for link in links:
        t = link.get("*", "")
        if t.startswith(prefix) and t not in pages and ":" not in t.split("/")[-1]:
            pages.append(t)
    return pages


def build_wikibooks_epub(book_title, dest_path, api=WIKIBOOKS_API,
                         source_name="Wikibooks contributors"):
    pages = _wikibooks_book_pages(book_title, api=api)
    chapters = []
    for page in pages:
        try:
            html_text = _wikibooks_page_html(page, api=api)
        except Exception:
            continue
        if not html_text:
            continue
        ex = _TextExtract()
        ex.feed(html_text)
        body = ex.text()
        if not body:
            continue
        label = page[len(book_title):].strip("/") or "Introduction"
        label = label.replace("_", " ")
        chapters.append((label, html_text))
    if not chapters:
        raise ValueError("Could not read any pages of that wiki book.")

    uid = slugify(source_name) + "-" + slugify(book_title)
    manifest_items, spine_items, files = [], [], {}
    nav_points = []
    for i, (label, html_text) in enumerate(chapters, start=1):
        fname = "chap%03d.xhtml" % i
        doc = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
            "<title>%s</title></head><body>%s</body></html>"
            % (html.escape(label), html_text)
        )
        files["OEBPS/" + fname] = doc.encode("utf-8")
        manifest_items.append(
            '<item id="c%d" href="%s" media-type="application/xhtml+xml"/>' % (i, fname)
        )
        spine_items.append('<itemref idref="c%d"/>' % i)
        nav_points.append(
            '<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text>'
            "</navLabel><content src=\"%s\"/></navPoint>"
            % (i, i, html.escape(label), fname)
        )
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:opf="http://www.idpf.org/2007/opf">'
        "<dc:title>%s</dc:title><dc:language>en</dc:language>"
        '<dc:identifier id="bookid">%s</dc:identifier>'
        "<dc:creator>%s</dc:creator></metadata>"
        "<manifest>%s"
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>'
        '<spine toc="ncx">%s</spine></package>'
        % (html.escape(book_title), uid, html.escape(source_name),
           "".join(manifest_items), "".join(spine_items))
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        "<head></head><docTitle><text>%s</text></docTitle>"
        "<navMap>%s</navMap></ncx>"
        % (html.escape(book_title), "".join(nav_points))
    )
    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(dest_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/toc.ncx", ncx)
        for name, blob in files.items():
            z.writestr(name, blob, zipfile.ZIP_DEFLATED)
    return dest_path


# --------------------------------------------------------------------------
# EPUB reading
# --------------------------------------------------------------------------

def read_epub_chapters(path):
    """Return [{'title': ..., 'text': ...}, ...] in spine order."""
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = None
        for el in container.iter():
            if el.tag.endswith("rootfile"):
                opf_path = el.get("full-path")
                break
        if not opf_path:
            raise ValueError("That EPUB has no package file.")
        opf = ET.fromstring(z.read(opf_path))
        base = os.path.dirname(opf_path)

        manifest = {}
        for item in opf.iter():
            if item.tag.endswith("item"):
                manifest[item.get("id")] = item.get("href")
        spine_ids = []
        for ref in opf.iter():
            if ref.tag.endswith("itemref"):
                spine_ids.append(ref.get("idref"))

        # NCX titles, when present, make nicer chapter names.
        ncx_titles = {}
        ncx_href = None
        for item in opf.iter():
            if item.tag.endswith("item") and (item.get("media-type") or "").endswith("ncx+xml"):
                ncx_href = item.get("href")
        if ncx_href:
            ncx_full = os.path.join(base, ncx_href) if base else ncx_href
            if ncx_full in names:
                try:
                    ncx = ET.fromstring(z.read(ncx_full))
                    for np in ncx.iter():
                        if np.tag.endswith("navPoint"):
                            label, src = None, None
                            for child in np.iter():
                                if child.tag.endswith("text") and label is None:
                                    label = (child.text or "").strip()
                                if child.tag.endswith("content"):
                                    src = (child.get("src") or "").split("#")[0]
                            if src and label:
                                ncx_titles[os.path.basename(src)] = label
                except Exception:
                    pass

        chapters = []
        for sid in spine_ids:
            href = manifest.get(sid)
            if not href:
                continue
            full = os.path.normpath(os.path.join(base, href)).replace(os.sep, "/")
            if full not in names:
                continue
            try:
                raw = z.read(full).decode("utf-8", "replace")
            except Exception:
                continue
            ex = _TextExtract()
            try:
                ex.feed(raw)
            except Exception:
                continue
            text = ex.text()
            if len(text) < 40:
                continue  # cover pages and other stubs are not chapters
            title = (
                ncx_titles.get(os.path.basename(full))
                or ex.title
                or "Chapter %d" % (len(chapters) + 1)
            )
            chapters.append({"title": title[:120], "text": text})
    if not chapters:
        raise ValueError("No readable text found in that EPUB.")
    return chapters


# --------------------------------------------------------------------------
# places (reading position) + library index
# --------------------------------------------------------------------------

def epub_title(path):
    """Best-effort dc:title from an EPUB's package file."""
    try:
        with zipfile.ZipFile(path) as z:
            container = ET.fromstring(z.read("META-INF/container.xml"))
            opf_path = None
            for el in container.iter():
                if el.tag.endswith("rootfile"):
                    opf_path = el.get("full-path")
                    break
            if not opf_path:
                return None
            opf = ET.fromstring(z.read(opf_path))
            for el in opf.iter():
                if el.tag.endswith("title") and el.text:
                    return " ".join(el.text.split())[:150]
    except Exception:
        pass
    return None


def read_book_chapters(path):
    """Dispatch on file type: EPUB, Word .docx, or basic text PDF."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return read_docx_chapters(path)
    if ext == ".pdf":
        return read_pdf_chapters(path)
    return read_epub_chapters(path)


# --------------------------------------------------------------------------
# Word .docx reading: a .docx is a zip; word/document.xml holds the text.
# Chapters split on Heading 1 / Title paragraphs when those exist.
# --------------------------------------------------------------------------

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_paragraphs(path):
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read("word/document.xml")
        except KeyError:
            raise ValueError("That file does not look like a Word .docx document.")
    doc = ET.fromstring(xml)
    paras = []
    for p in doc.iter(_W_NS + "p"):
        style = ""
        ppr = p.find(_W_NS + "pPr")
        if ppr is not None:
            st = ppr.find(_W_NS + "pStyle")
            if st is not None:
                style = st.get(_W_NS + "val", "") or ""
        text = "".join(t.text or "" for t in p.iter(_W_NS + "t"))
        paras.append((style, " ".join(text.split())))
    return paras


def read_docx_chapters(path):
    paras = _docx_paragraphs(path)
    chapters = []
    title, lines = "Document", []

    def flush():
        body = "\n\n".join(lines).strip()
        if body:
            chapters.append({"title": title[:120], "text": body})

    for style, text in paras:
        low = style.lower()
        if ("heading1" in low or low == "title") and text:
            flush()
            title, lines = text, []
        elif text:
            lines.append(text)
    flush()
    if not chapters:
        raise ValueError("No readable text found in that document.")
    # A single un-headed document still reads better in pieces.
    if len(chapters) == 1 and len(chapters[0]["text"]) > 14000:
        body = chapters[0]["text"]
        paras2 = body.split("\n\n")
        chunks, cur = [], ""
        for para in paras2:
            if len(cur) + len(para) > 12000 and cur:
                chunks.append(cur)
                cur = ""
            cur = (cur + "\n\n" + para) if cur else para
        if cur:
            chunks.append(cur)
        chapters = [
            {"title": "Part %d" % (i + 1), "text": c} for i, c in enumerate(chunks)
        ]
    return chapters


def docx_title(path):
    try:
        with zipfile.ZipFile(path) as z:
            core = ET.fromstring(z.read("docProps/core.xml"))
            for el in core.iter():
                if el.tag.endswith("title") and el.text:
                    return " ".join(el.text.split())[:150]
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# PDF reading: pull text out of content streams. Handles the filter
# chains real generators use (FlateDecode, ASCII85Decode + FlateDecode)
# and custom-encoded fonts through their ToUnicode maps. Works on
# text-based PDFs; scanned/image PDFs have no text and are reported.
# --------------------------------------------------------------------------

import base64 as _b64

_WINANSI_MAP = {
    0x85: "...", 0x91: "'", 0x92: "'", 0x93: '"', 0x94: '"',
    0x95: "-", 0x96: "-", 0x97: "--", 0xA0: " ",
}


def _pdf_unescape(raw):
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):  # backslash
            n = raw[i + 1]
            if n in b"nrtbf":
                out += {ord("n"): b"\n", ord("r"): b"", ord("t"): b" ",
                        ord("b"): b"", ord("f"): b""}[n]
                i += 2
            elif n in b"()\\":
                out.append(n)
                i += 2
            elif 0x30 <= n <= 0x37:  # octal, up to 3 digits
                j = i + 1
                digits = b""
                while j < len(raw) and len(digits) < 3 and 0x30 <= raw[j] <= 0x37:
                    digits += bytes([raw[j]])
                    j += 1
                out.append(int(digits, 8) & 0xFF)
                i = j
            else:
                i += 2
        else:
            out.append(c)
            i += 1
    return bytes(out)


def _pdf_decode_bytes(raw):
    text = raw.decode("latin-1")
    return "".join(_WINANSI_MAP.get(ord(ch), ch) for ch in text)


def _pdf_objects(data):
    """{objnum: (dict_bytes, stream_bytes_or_None)} for the whole file."""
    objects = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b", data):
        num = int(m.group(1))
        start = m.end()
        end = data.find(b"endobj", start)
        if end == -1:
            continue
        body = data[start:end]
        sm = re.search(rb"stream\r?\n", body)
        if sm:
            send = body.find(b"endstream", sm.end())
            dict_part = body[:sm.start()]
            stream = body[sm.end():send] if send != -1 else body[sm.end():]
            objects[num] = (dict_part, stream.rstrip(b"\r\n"))
        else:
            objects[num] = (body, None)
    return objects


def _pdf_decode_stream(dict_part, blob):
    if blob is None:
        return None
    filters = []
    fm = re.search(rb"/Filter\s*(\[[^\]]*\]|/\w+)", dict_part)
    if fm:
        filters = [f.decode() for f in re.findall(rb"/(\w+)", fm.group(1))]
    out = blob
    for name in filters:
        try:
            if name == "FlateDecode":
                out = zlib.decompress(out)
            elif name == "ASCII85Decode":
                cleaned = out.strip()
                if cleaned.startswith(b"<~"):
                    cleaned = cleaned[2:]
                if cleaned.endswith(b"~>"):
                    cleaned = cleaned[:-2]
                out = _b64.a85decode(cleaned.strip(), adobe=False)
            else:
                return None  # a filter this simple reader does not know
        except Exception:
            try:
                out = zlib.decompress(out) if name == "FlateDecode" else out
            except Exception:
                return None
    return out


def _pdf_parse_cmap(content):
    """Parse a ToUnicode CMap into ({code: text}, code_byte_length)."""
    mapping = {}
    code_len = 2
    text = content.decode("latin-1", "replace")

    def dst_text(hexs):
        raw = bytes.fromhex(hexs)
        try:
            return raw.decode("utf-16-be")
        except Exception:
            return _pdf_decode_bytes(raw)

    for m in re.finditer(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            code_len = max(1, len(src) // 2)
            mapping[int(src, 16)] = dst_text(dst)
    for m in re.finditer(r"beginbfrange(.*?)endbfrange", text, re.S):
        body = m.group(1)
        for lo, hi, dst in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", body
        ):
            code_len = max(1, len(lo) // 2)
            base = int(dst, 16)
            for code in range(int(lo, 16), int(hi, 16) + 1):
                raw = (base + (code - int(lo, 16))).to_bytes(len(dst) // 2, "big")
                try:
                    mapping[code] = raw.decode("utf-16-be")
                except Exception:
                    mapping[code] = _pdf_decode_bytes(raw)
        for lo, hi, arr in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[([^\]]*)\]", body
        ):
            dsts = re.findall(r"<([0-9A-Fa-f]+)>", arr)
            for off, dst in enumerate(dsts):
                mapping[int(lo, 16) + off] = dst_text(dst)
    return mapping, code_len


def _pdf_font_cmaps(objects, decoded):
    """{resource_name: (mapping, code_len)} from font dicts + ToUnicode."""
    cmaps = {}
    for num, content in decoded.items():
        if content and (b"beginbfchar" in content or b"beginbfrange" in content):
            cmaps[num] = _pdf_parse_cmap(content)
    name_to_cmap = {}
    font_objs = {}
    for num, (dict_part, _s) in objects.items():
        tm = re.search(rb"/ToUnicode\s+(\d+)\s+\d+\s+R", dict_part)
        if tm:
            font_objs[num] = int(tm.group(1))
    for num, (dict_part, _s) in objects.items():
        for fm in re.finditer(rb"/Font\s*<<(.*?)>>", dict_part, re.S):
            for name, ref in re.findall(rb"/(\w+)\s+(\d+)\s+\d+\s+R", fm.group(1)):
                cmap_obj = font_objs.get(int(ref))
                if cmap_obj in cmaps:
                    name_to_cmap[name.decode()] = cmaps[cmap_obj]
    return name_to_cmap


def _pdf_cmap_decode(raw, cmap):
    mapping, code_len = cmap
    if code_len <= 1:
        return "".join(mapping.get(b, _pdf_decode_bytes(bytes([b]))) for b in raw)
    out = []
    for i in range(0, len(raw) - 1, 2):
        code = (raw[i] << 8) | raw[i + 1]
        out.append(mapping.get(code, ""))
    return "".join(out)


def _pdf_content_lines(content, font_cmaps):
    """Walk a content stream, tracking the current font, and pull out
    the text of each Tj / TJ show operation as one line."""
    lines = []
    current = [None]  # (mapping, code_len) for the active font

    def decode(raw):
        if current[0]:
            return _pdf_cmap_decode(raw, current[0])
        return _pdf_decode_bytes(raw)

    i, n = 0, len(content)
    while i < n:
        tf = re.match(rb"/(\w+)\s+[\d.]+\s+Tf", content[i:])
        if tf:
            current[0] = font_cmaps.get(tf.group(1).decode())
            i += tf.end()
            continue
        if content[i:i + 1] == b"[":
            # A TJ array: its strings are one line of text, kerning
            # numbers and all. Decode and join them without breaks.
            j = content.find(b"]", i)
            if j != -1 and re.match(rb"\s*TJ", content[j + 1:j + 6]):
                segment = content[i:j + 1]
                parts = []
                for sm in re.finditer(rb"\((?:\\.|[^\\()])*\\)|<([0-9A-Fa-f\s]+)>", segment):
                    token = sm.group(0)
                    if token.startswith(b"("):
                        parts.append(decode(_pdf_unescape(token[1:-1])))
                    else:
                        hexpart = re.sub(rb"\s+", b"", sm.group(1))
                        if len(hexpart) % 2:
                            hexpart += b"0"
                        try:
                            parts.append(decode(bytes.fromhex(hexpart.decode())))
                        except Exception:
                            pass
                joined = "".join(parts).strip()
                if joined:
                    lines.append(joined)
                i = j + 1
                continue
        c = content[i:i + 1]
        if c == b"(":
            depth, j, buf = 1, i + 1, bytearray()
            while j < n and depth:
                ch = content[j]
                if ch == 0x5C and j + 1 < n:
                    buf += content[j:j + 2]
                    j += 2
                    continue
                if ch == 0x28:
                    depth += 1
                elif ch == 0x29:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                buf.append(ch)
                j += 1
            tail = content[j:j + 14]
            if re.match(rb"\s*(Tj|TJ|'|\")", tail):
                lines.append(decode(_pdf_unescape(bytes(buf))))
            i = j
        elif c == b"<" and content[i:i + 2] != b"<<":
            j = content.find(b">", i)
            if j == -1:
                break
            hexpart = re.sub(rb"\s+", b"", content[i + 1:j])
            if hexpart and re.match(rb"^[0-9A-Fa-f]+$", hexpart):
                if len(hexpart) % 2:
                    hexpart += b"0"
                try:
                    lines.append(decode(bytes.fromhex(hexpart.decode())))
                except Exception:
                    pass
            i = j + 1
        else:
            i += 1
    return lines


def _pdf_join_fragments(lines):
    """Glue word fragments that PDF renderers split across show
    operations ('Y' + 'our way', 'Quick S' + 'tart:', 'doesn' + '’t')."""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out:
            prev = out[-1]
            last_word = prev.rsplit(" ", 1)[-1] if prev else ""
            glue = False
            if len(prev) == 1 and line[0].islower():
                glue = True
            elif len(line) == 1 and line.islower() and prev[-1:].isalpha():
                glue = True
            elif len(last_word) == 1 and last_word.isalpha() and line[0].islower():
                glue = True
            elif (
                line[0] in "'’"
                and len(last_word) <= 4
                and last_word.isalpha()
            ):
                glue = True
            elif (
                line[0].islower()
                and len(last_word) <= 2
                and last_word.isalpha()
                and not prev.endswith((".", "!", "?", ":", ";"))
            ):
                glue = True
            if glue:
                out[-1] = prev + line
                continue
        out.append(line)
    return out


def read_pdf_chapters(path, pages_per_chapter=5):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"%PDF":
        raise ValueError("That file does not look like a PDF.")
    objects = _pdf_objects(data)
    decoded = {}
    for num, (dict_part, blob) in objects.items():
        if blob is not None:
            content = _pdf_decode_stream(dict_part, blob)
            if content is not None:
                decoded[num] = content
    font_cmaps = _pdf_font_cmaps(objects, decoded)

    def content_lines(num):
        content = decoded.get(num)
        if not content or (b"Tj" not in content and b"TJ" not in content):
            return []
        raw = [ln for ln in _pdf_content_lines(content, font_cmaps) if ln.strip()]
        return _pdf_join_fragments(raw)

    # Page order from the Pages tree when it can be found.
    page_nums = []
    for num, (dict_part, _s) in objects.items():
        if b"/Type" in dict_part and b"/Pages" in dict_part and b"/Kids" in dict_part:
            km = re.search(rb"/Kids\s*\[([^\]]*)\]", dict_part)
            if km:
                page_nums = [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", km.group(1))]
                break
    pages = []
    if page_nums:
        for pnum in page_nums:
            dict_part = objects.get(pnum, (b"", None))[0]
            cm = re.search(rb"/Contents\s+(\d+)\s+\d+\s+R", dict_part)
            refs = []
            if cm:
                refs = [int(cm.group(1))]
            else:
                am = re.search(rb"/Contents\s*\[([^\]]*)\]", dict_part)
                if am:
                    refs = [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", am.group(1))]
            lines = []
            for r in refs:
                lines += content_lines(r)
            if lines:
                pages.append("\n".join(lines))
    if not pages:
        for num in sorted(decoded):
            lines = content_lines(num)
            if lines:
                pages.append("\n".join(lines))
    if not pages:
        raise ValueError(
            "No readable text in that PDF. It is probably scanned images; "
            "this reader handles text-based PDFs only."
        )
    chapters = []
    for i in range(0, len(pages), pages_per_chapter):
        group = pages[i:i + pages_per_chapter]
        chapters.append(
            {
                "title": "Pages %d-%d" % (i + 1, i + len(group)),
                "text": "\n\n".join(group),
            }
        )
    return chapters


def get_place(book_id):
    places = load_json(PLACES_JSON, {})
    return places.get(book_id) or {"chapter": 0, "fraction": 0.0}


def set_place(book_id, chapter, fraction):
    places = load_json(PLACES_JSON, {})
    places[book_id] = {
        "chapter": int(chapter),
        "fraction": float(fraction),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_json(PLACES_JSON, places)


def get_library():
    return load_json(LIBRARY_JSON, [])


def add_to_library(record):
    lib = get_library()
    lib = [b for b in lib if b.get("id") != record["id"]]
    lib.insert(0, record)
    save_json(LIBRARY_JSON, lib)
    return lib


# --------------------------------------------------------------------------
# self-test (no window): search both sources, fetch a book, parse it
# --------------------------------------------------------------------------

def selftest():
    ensure_dirs()
    print("== Gutenberg search: 'Frankenstein' ==")
    results = search_gutenberg("Frankenstein", limit=5)
    for r in results:
        print(" -", r["title"], "|", r["author"], "| epub:", bool(r["epub_url"]))
    pick = next((r for r in results if r["epub_url"]), results[0])
    tmp = os.path.join(DATA_DIR, "selftest.epub")
    print("Downloading:", pick["title"])
    download_gutenberg_epub(pick, tmp)
    chapters = read_epub_chapters(tmp)
    print("Chapters parsed:", len(chapters))
    print("First chapter:", chapters[0]["title"], "| chars:", len(chapters[0]["text"]))
    set_place("selftest", 3, 0.42)
    place = get_place("selftest")
    assert place["chapter"] == 3 and abs(place["fraction"] - 0.42) < 1e-9, place
    print("Place save/load OK:", place)

    print("== Wikibooks search: 'Algebra' ==")
    wb = search_wikibooks("Algebra", limit=5)
    for r in wb:
        print(" -", r["title"])
    if wb:
        tmp2 = os.path.join(DATA_DIR, "selftest-wikibooks.epub")
        print("Fetching Wikibooks EPUB:", wb[0]["title"])
        fetch_wikibooks_epub(wb[0], tmp2)
        ch2 = read_epub_chapters(tmp2)
        print("Wikibooks chapters parsed:", len(ch2), "| first:", ch2[0]["title"])

    print("== Internet Archive search: 'Frankenstein' ==")
    ia = search_internet_archive("Frankenstein", limit=4, probe=12)
    for r in ia:
        print(" -", r["title"], "|", r.get("ext"))
    if ia:
        tmp3 = os.path.join(DATA_DIR, "selftest-ia" + ia[0]["ext"])
        print("Downloading from Archive:", ia[0]["title"])
        download_direct(ia[0], tmp3)
        ch3 = read_book_chapters(tmp3)
        print("Archive chapters parsed:", len(ch3))

    print("== Open Library search: 'Dracula' ==")
    ol = search_open_library("Dracula", limit=4, probe=10)
    for r in ol:
        print(" -", r["title"], "|", r["author"], "|", r.get("ext"))

    print("== Standard Ebooks search: 'Dracula' ==")
    se = search_standard_ebooks("Dracula", limit=3)
    for r in se:
        print(" -", r["title"], "|", r["author"])
    if se:
        tmp4 = os.path.join(DATA_DIR, "selftest-se.epub")
        print("Downloading from Standard Ebooks:", se[0]["title"])
        download_direct(se[0], tmp4)
        ch4 = read_epub_chapters(tmp4)
        print("Standard Ebooks chapters parsed:", len(ch4))

    print("== Wikisource search: 'Time Machine' ==")
    ws = search_wikisource("Time Machine", limit=5)
    for r in ws:
        print(" -", r["title"])
    if ws:
        pick = next((r for r in ws if r["title"] == "The Time Machine"), ws[0])
        tmp5 = os.path.join(DATA_DIR, "selftest-wikisource.epub")
        print("Fetching Wikisource EPUB:", pick["title"])
        fetch_wikisource_epub(pick, tmp5)
        ch5 = read_epub_chapters(tmp5)
        print("Wikisource chapters parsed:", len(ch5))
    print("SELFTEST DONE")




# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

def run_gui():
    import queue
    import tkinter as tk
    from tkinter import messagebox, ttk

    ensure_dirs()

    root = tk.Tk()
    root.title(APP_NAME)
    try:
        root.iconbitmap(resource_path("LibraryApp.ico"))
    except Exception as e:
        if os.name == "nt":  # .ico window icons are a Windows thing
            log_problem("window icon did not load: %r" % (e,))
    root.geometry("1080x720")
    root.minsize(820, 520)

    jobs = queue.Queue()

    # Tech Bench banner across the top, when the image ships with the app.
    # Never fatal, but never silent either: a windowed exe has no console,
    # so anything that stops the banner goes to LibraryData/app.log.
    banner_path = resource_path("banner.png")
    if not os.path.exists(banner_path):
        log_problem(
            "banner.png not found (frozen=%s). Looked in: %s"
            % (getattr(sys, "frozen", False),
               "; ".join(resource_candidates("banner.png"))))
    else:
        try:
            banner_img = tk.PhotoImage(master=root, file=banner_path)
            banner_lbl = tk.Label(root, image=banner_img, bg="#171008", bd=0)
            banner_lbl.image = banner_img  # keep a reference alive
            banner_lbl.pack(side=tk.TOP, fill=tk.X)
        except Exception as e:
            log_problem("banner.png found at %s but did not load (Tk %s): %r"
                        % (banner_path, tk.TkVersion, e))

    state = {
        "mode": "library",          # or "search"
        "items": [],                # rows backing the left list
        "book": None,               # open book record
        "chapters": [],
        "font_size": 13,
    }

    # ---- layout -----------------------------------------------------------
    top = ttk.Frame(root, padding=8)
    top.pack(side=tk.TOP, fill=tk.X)

    ttk.Label(top, text="Search:").pack(side=tk.LEFT)
    query_var = tk.StringVar()
    query_entry = ttk.Entry(top, textvariable=query_var, width=38)
    query_entry.pack(side=tk.LEFT, padx=(4, 6))

    src_gb = tk.BooleanVar(value=True)
    src_wb = tk.BooleanVar(value=True)
    src_ia = tk.BooleanVar(value=True)
    src_ol = tk.BooleanVar(value=False)
    src_se = tk.BooleanVar(value=False)
    src_ws = tk.BooleanVar(value=False)
    src_row = ttk.Frame(top)
    src_row.pack(side=tk.LEFT, padx=(2, 0))
    ttk.Checkbutton(src_row, text="Project Gutenberg", variable=src_gb).pack(side=tk.LEFT)
    ttk.Checkbutton(src_row, text="Wikibooks", variable=src_wb).pack(side=tk.LEFT)
    ttk.Checkbutton(src_row, text="Internet Archive", variable=src_ia).pack(side=tk.LEFT)
    ttk.Checkbutton(src_row, text="Open Library", variable=src_ol).pack(side=tk.LEFT)
    ttk.Checkbutton(src_row, text="Standard Ebooks", variable=src_se).pack(side=tk.LEFT)
    ttk.Checkbutton(src_row, text="Wikisource", variable=src_ws).pack(side=tk.LEFT)

    status_var = tk.StringVar(value="Your library is on the left. Search above for new books.")
    status = ttk.Label(root, textvariable=status_var, padding=(8, 0))
    status.pack(side=tk.TOP, fill=tk.X)

    body = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
    body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    left = ttk.Frame(body, width=330)
    right = ttk.Frame(body)
    body.add(left, weight=1)
    body.add(right, weight=3)

    mode_row = ttk.Frame(left)
    mode_row.pack(fill=tk.X, pady=(0, 6))
    lib_btn = ttk.Button(mode_row, text="My Library")
    search_btn = ttk.Button(mode_row, text="Search Results")
    lib_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
    search_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))

    listbox = tk.Listbox(left, activestyle="dotbox", font=("Segoe UI", 10))
    listbox.pack(fill=tk.BOTH, expand=True)
    remove_btn = ttk.Button(left, text="Remove selected book")
    remove_btn.pack(fill=tk.X, pady=(6, 0))

    # reader
    chap_row = ttk.Frame(right)
    chap_row.pack(fill=tk.X, pady=(0, 6))
    prev_btn = ttk.Button(chap_row, text="<< Prev")
    next_btn = ttk.Button(chap_row, text="Next >>")
    prev_btn.pack(side=tk.LEFT)
    next_btn.pack(side=tk.LEFT, padx=(6, 12))
    chap_var = tk.StringVar(value="")
    chap_menu = ttk.Combobox(chap_row, textvariable=chap_var, state="readonly", width=52)
    chap_menu.pack(side=tk.LEFT, fill=tk.X, expand=True)
    smaller_btn = ttk.Button(chap_row, text="A-")
    bigger_btn = ttk.Button(chap_row, text="A+")
    smaller_btn.pack(side=tk.RIGHT)
    bigger_btn.pack(side=tk.RIGHT, padx=(0, 6))

    title_var = tk.StringVar(value="No book open")
    ttk.Label(right, textvariable=title_var, font=("Segoe UI", 13, "bold")).pack(
        fill=tk.X, pady=(0, 4)
    )

    text_frame = ttk.Frame(right)
    text_frame.pack(fill=tk.BOTH, expand=True)
    scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
    text = tk.Text(
        text_frame,
        wrap=tk.WORD,
        font=("Georgia", state["font_size"]),
        padx=18,
        pady=12,
        yscrollcommand=scrollbar.set,
        undo=False,
    )
    scrollbar.config(command=text.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    text.insert("1.0", "Open a book from your library, or search for a new one above.\n\n"
                         "Your place is saved automatically as you read.")
    text.config(state=tk.DISABLED)

    SOURCE_LABELS = {
        "gutenberg": "Gutenberg",
        "wikibooks": "Wikibooks",
        "wikisource": "Wikisource",
        "archive": "Internet Archive",
        "openlibrary": "Open Library",
        "standardebooks": "Standard Ebooks",
        "local": "Local file",
    }

    # ---- left list --------------------------------------------------------
    def refresh_list():
        listbox.delete(0, tk.END)
        if state["mode"] == "library":
            items = get_library()
            for b in items:
                listbox.insert(tk.END, b["title"])
            state["items"] = items
            remove_btn.config(state=tk.NORMAL)
        else:
            for b in state["items"]:
                tag = SOURCE_LABELS.get(b["source"], b["source"])
                line = b["title"]
                if b.get("author"):
                    line += " — " + b["author"]
                listbox.insert(tk.END, "[%s] %s" % (tag, line))
            remove_btn.config(state=tk.DISABLED)
        lib_btn.state(["disabled"] if state["mode"] == "library" else ["!disabled"])
        search_btn.state(["disabled"] if state["mode"] == "search" else ["!disabled"])

    def show_library():
        state["mode"] = "library"
        refresh_list()
        status_var.set("Your downloaded books. Double-click one to read it.")

    def show_search():
        state["mode"] = "search"
        refresh_list()
        status_var.set("Double-click a result to download it and start reading.")

    lib_btn.config(command=show_library)
    search_btn.config(command=show_search)

    # ---- searching --------------------------------------------------------
    def do_search():
        q = query_var.get().strip()
        if not q:
            return
        chosen = [
            ("Project Gutenberg", src_gb.get(), search_gutenberg),
            ("Wikibooks", src_wb.get(), search_wikibooks),
            ("Internet Archive", src_ia.get(), search_internet_archive),
            ("Open Library", src_ol.get(), search_open_library),
            ("Standard Ebooks", src_se.get(), search_standard_ebooks),
            ("Wikisource", src_ws.get(), search_wikisource),
        ]
        active = [(name, fn) for name, on, fn in chosen if on]
        if not active:
            messagebox.showinfo(APP_NAME, "Tick at least one source to search.")
            return
        status_var.set("Searching...")

        def work():
            found, errors = [], []
            for name, fn in active:
                try:
                    found += fn(q)
                except Exception as e:
                    errors.append("%s: %s" % (name, e))
            jobs.put(("search_done", found, errors))

        threading.Thread(target=work, daemon=True).start()

    ttk.Button(top, text="Search", command=do_search).pack(side=tk.LEFT, padx=(8, 0))
    query_entry.bind("<Return>", lambda e: do_search())

    # ---- opening books ----------------------------------------------------
    def open_book(record, chapters=None):
        try:
            if chapters is None:
                chapters = read_book_chapters(record["path"])
        except Exception as e:
            messagebox.showerror(APP_NAME, "Could not open that book:\n%s" % e)
            return
        save_current_place()
        state["book"] = record
        state["chapters"] = chapters
        title_var.set(record["title"])
        chap_menu.config(values=[c["title"] for c in chapters])
        place = get_place(record["id"])
        idx = min(place.get("chapter", 0), len(chapters) - 1)
        show_chapter(idx, fraction=place.get("fraction", 0.0))
        status_var.set("Now reading: %s" % record["title"])

    def show_chapter(idx, fraction=0.0):
        chapters = state["chapters"]
        if not chapters:
            return
        idx = max(0, min(idx, len(chapters) - 1))
        state["chapter"] = idx
        ch = chapters[idx]
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        text.insert("1.0", ch["text"])
        text.config(state=tk.DISABLED)
        chap_var.set(ch["title"])
        root.update_idletasks()
        try:
            text.yview_moveto(fraction)
        except Exception:
            pass
        prev_btn.config(state=tk.NORMAL if idx > 0 else tk.DISABLED)
        next_btn.config(state=tk.NORMAL if idx < len(chapters) - 1 else tk.DISABLED)
        if state["book"]:
            set_place(state["book"]["id"], idx, fraction)

    def save_current_place():
        if state.get("book") and state.get("chapters"):
            try:
                frac = text.yview()[0]
            except Exception:
                frac = 0.0
            set_place(state["book"]["id"], state.get("chapter", 0), frac)

    prev_btn.config(command=lambda: show_chapter(state.get("chapter", 0) - 1))
    next_btn.config(command=lambda: show_chapter(state.get("chapter", 0) + 1))

    def chapter_picked(_event=None):
        title = chap_var.get()
        for i, c in enumerate(state["chapters"]):
            if c["title"] == title:
                show_chapter(i)
                break

    chap_menu.bind("<<ComboboxSelected>>", chapter_picked)

    def set_font(delta):
        state["font_size"] = max(9, min(26, state["font_size"] + delta))
        text.config(font=("Georgia", state["font_size"]))

    smaller_btn.config(command=lambda: set_font(-1))
    bigger_btn.config(command=lambda: set_font(+1))

    def on_double_click(_event=None):
        sel = listbox.curselection()
        if not sel:
            return
        item = state["items"][sel[0]]
        if state["mode"] == "library":
            open_book(item)
            return
        # search result: download, file it, open it
        status_var.set("Downloading: %s ..." % item["title"])

        def work():
            try:
                ext = item.get("ext") or ".epub"
                dest = os.path.join(BOOKS_DIR, item["id"] + ext)
                if item["source"] == "gutenberg":
                    download_gutenberg_epub(item, dest)
                elif item["source"] == "wikibooks":
                    fetch_wikibooks_epub(item, dest)
                elif item["source"] == "wikisource":
                    fetch_wikisource_epub(item, dest)
                else:
                    download_direct(item, dest)
                record = {
                    "id": item["id"],
                    "title": item["title"],
                    "author": item.get("author", ""),
                    "source": item["source"],
                    "path": dest,
                    "added": time.strftime("%Y-%m-%d"),
                }
                add_to_library(record)
                chapters = read_book_chapters(dest)
                jobs.put(("downloaded", record, chapters))
            except Exception as e:
                jobs.put(("error", "Download failed: %s" % e))

        threading.Thread(target=work, daemon=True).start()

    listbox.bind("<Double-Button-1>", on_double_click)

    import hashlib
    import shutil
    from tkinter import filedialog

    def open_local_file():
        path = filedialog.askopenfilename(
            title="Open a book file",
            filetypes=[
                ("Books", "*.epub *.docx *.pdf"),
                ("EPUB books", "*.epub"),
                ("Word documents", "*.docx"),
                ("PDF documents", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".epub", ".docx", ".pdf"):
            messagebox.showinfo(
                APP_NAME, "That file type is not supported. EPUB, .docx and PDF are."
            )
            return
        try:
            with open(path, "rb") as f:
                digest = hashlib.md5(f.read()).hexdigest()[:10]
            book_id = "local-" + digest
            dest = os.path.join(BOOKS_DIR, book_id + ext)
            if not os.path.exists(dest):
                shutil.copyfile(path, dest)
            if ext == ".epub":
                title = epub_title(dest)
            elif ext == ".docx":
                title = docx_title(dest)
            else:
                title = None
            record = {
                "id": book_id,
                "title": title or os.path.splitext(os.path.basename(path))[0],
                "author": "",
                "source": "local",
                "path": dest,
                "added": time.strftime("%Y-%m-%d"),
            }
            add_to_library(record)
            chapters = read_book_chapters(dest)
            open_book(record, chapters=chapters)
            status_var.set("Opened local file: %s" % record["title"])
        except Exception as e:
            messagebox.showerror(APP_NAME, "Could not open that file:\n%s" % e)

    local_btn = ttk.Button(left, text="Open local file (EPUB, Word, PDF)...", command=open_local_file)
    local_btn.pack(fill=tk.X, pady=(6, 0))

    def remove_selected():
        if state["mode"] != "library":
            return
        sel = listbox.curselection()
        if not sel:
            return
        item = state["items"][sel[0]]
        if not messagebox.askyesno(APP_NAME, "Remove '%s' and its file?" % item["title"]):
            return
        try:
            os.remove(item["path"])
        except Exception:
            pass
        lib = [b for b in get_library() if b.get("id") != item["id"]]
        save_json(LIBRARY_JSON, lib)
        if state.get("book") and state["book"]["id"] == item["id"]:
            state["book"] = None
            state["chapters"] = []
        refresh_list()
        status_var.set("Removed: %s" % item["title"])

    remove_btn.config(command=remove_selected)

    # ---- background job pump + autosave ----------------------------------
    def pump():
        try:
            while True:
                job = jobs.get_nowait()
                if job[0] == "search_done":
                    _, found, errors = job
                    state["items"] = found
                    state["mode"] = "search"
                    refresh_list()
                    msg = "Found %d book(s)." % len(found)
                    if errors:
                        msg += " Some sources failed: " + "; ".join(errors)
                    status_var.set(msg)
                elif job[0] == "downloaded":
                    _, record, chapters = job
                    open_book(record, chapters=chapters)
                    if state["mode"] != "library":
                        pass
                elif job[0] == "error":
                    status_var.set(job[1])
                    messagebox.showerror(APP_NAME, job[1])
        except queue.Empty:
            pass
        root.after(120, pump)

    def autosave():
        save_current_place()
        root.after(15000, autosave)

    def on_close():
        save_current_place()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_list()
    pump()
    autosave()
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_gui()
