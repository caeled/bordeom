# Everyday Cool Library App

One of the very Everyday Cool things about the intenet is the vast number of free books availabile from a number of sources. This app puts six of those sources in one small Windows window: search them, download a book, and start reading, with your place saved for when you come back.

An [Everyday Cool](https://github.com/caeled/everyday-cool) subproject.

## Web edition

`web/index.html` is a hosted version of the same library: one static page, no server code, so it runs on any static host (GitHub Pages, a home server, Neocities).

- **Wikibooks and Wikisource read natively in the page**, and so do EPUB files you open from your own device. Your library list and reading places are kept in the browser's local storage.
- **Project Gutenberg, Internet Archive and Open Library will not let other pages fetch their book files** (the browser's CORS rule). Without help, the web edition searches and then hands you to the source's own reader: Archive and Open Library results read in an embedded Archive reader panel, Gutenberg results open at gutenberg.org, and **Standard Ebooks** cannot be offered at all.
- **With the home-server proxy running (below), that wall comes down**: all six sources read natively in the page, places saved, no hand-offs.

### Home-server proxy (optional, for the web edition)

`proxy/library-proxy.py` is a tiny fetch proxy (Python standard library only, like the app). Run it on the same machine that hosts the web edition:

```
python proxy/library-proxy.py          (or double-click proxy/library-proxy.bat)
```

It listens on port 8766. The web page checks its own host on that port automatically; when the proxy answers, Gutenberg, Archive and Open Library books are fetched through it and read in the page, and the Standard Ebooks source switches on. If you run the proxy on a different host or port, set the page's `ecl_proxy` localStorage key to its base URL (for example `http://myserver:8766`).

The proxy only fetches from the library's own book sources (an allowlist in the script), and it is meant for your own home network. Do not expose it to the open internet. The desktop app does not need it.

## Sources

Tick any combination at the top, type a title or author, hit Search.

- **Project Gutenberg** — the classic public-domain library (on by default).
- **Wikibooks** — open textbooks, built into EPUBs on the fly (on by default).
- **Internet Archive** — the big one, millions of texts (on by default). Only items archive.org offers as an unrestricted download are shown; its lending-only books are filtered out rather than failing at download time. Some Archive books come down as PDFs instead of EPUBs; the reader handles both.
- **Open Library** — archive.org's sister catalog. Different search, same open stock underneath; handy when an Archive search is noisy.
- **Standard Ebooks** — about a thousand public-domain titles, the best-produced EPUBs of the lot. (Their OPDS feed is members-only, so the app goes through the public website instead.)
- **Wikisource** — public-domain works, exported to EPUB. Pick a specific edition when search offers several (for example "The Time Machine (Heinemann text)"); a bare title page with no edition is usually just an index and exports thin.

Archive and Standard Ebooks checks make those searches slower than Gutenberg's. That is the libraries answering, not the app stuck.

## Reading

- **Double-click a result** to download the book and start reading. Downloaded books land in **My Library** (left side).
- **Open local file (EPUB, Word, PDF)...** (under the book list) opens a book you already have on disk. It is copied into your library, titled from the book's own metadata where it has any, and your place is saved for it like any other book. Opening the same file twice does not duplicate it.
  - Word means **.docx** (the modern format). Chapters split on Heading 1 / Title paragraphs when the document has them.
  - PDF means **text-based PDFs**: documents exported from Word, Google Docs, and similar extract cleanly, in page order, grouped five pages to a chapter. Scanned PDFs are images and have no text to read. Design-heavy PDFs (chart reports, brochures) extract with some spacing artifacts, though the text is all there.
- **Reading**: chapter list at the top of the reader, Prev / Next buttons, and A- / A+ for text size.
- **Your place is saved automatically** as you read (checked every few seconds and when you close the app). Reopen a book and you are back on the same chapter, at the same scroll position.
- **Remove selected book** deletes a downloaded book and its file.

## Run it

Needs Python 3 on the machine. Nothing else to install: the app uses only the Python standard library.

Double-click **LibraryApp.bat** (or run `python LibraryApp.py`).

## Build a Windows executable

Double-click **build.bat** (or run it from a Command Prompt in this folder). It installs PyInstaller, builds from `LibraryApp.py` with the banner and icon baked in, and checks that `banner.png` made it into the bundle. The command it runs is:

```
python -m PyInstaller --noconfirm --clean --windowed --icon LibraryApp.ico --name LibraryApp --add-data "banner.png;." --add-data "LibraryApp.ico;." LibraryApp.py
```

You get `dist\LibraryApp\LibraryApp.exe`. Run that one (with its `_internal` folder beside it), not the copy under `build\`. Books and reading places live in a `LibraryData` folder next to the exe.

Two things to know when rebuilding:

- **Do not build with `pyinstaller LibraryApp.spec`.** A `.spec` file left over from an earlier build keeps that build's data list and ignores `--add-data`, so the banner can drop out. `build.bat` deletes any old spec first.
- **PyInstaller wipes `dist\LibraryApp` on every build, `LibraryData` included.** `build.bat` moves `LibraryData` aside and puts it back afterwards. If you run the PyInstaller command by hand, copy `LibraryData` out first.

## Where things live

Everything sits in a `LibraryData` folder next to the app:

- `LibraryData\Books\` — the book files
- `LibraryData\library.json` — your downloaded books
- `LibraryData\places.json` — reading position per book

Move or back up that folder and your library and places move with it.

## Icon and banner

`LibraryApp.ico` (a stack of books) is the app's window icon; it is also in the folder as `bookstack.png`. `banner.png` is a small version of the Everyday Cool Tech Bench banner, meant to run across the top of the window.

## Known issues

- **The Tech Bench banner does not appear in the PyInstaller-built executable** ([#1](https://github.com/caeled/everyday-cool-library-app/issues/1)). Rebuild with `build.bat`. If the banner is still missing, the app now writes the reason (where it looked, or why the image would not load) to `LibraryData\app.log` instead of skipping it silently.

## Licenses

Same terms as the rest of Everyday Cool: code is MIT (see `LICENSE`); original writing is CC BY 4.0 (see `LICENSE-CONTENT.md`). Books you download keep their own sources' terms.
