# Reference Loaders — online first, home server as the backup

Built 2026-11-24. One small page per site. The loader sits where the page
lives on PowellServer, under the page's **original** filename, so every
existing link and bookmark hits it first. When opened it:

1. Shows **"Trying to load latest build from GitHub…"** and probes the live
   GitHub Pages build (6-second timeout).
2. If GitHub answers, it hands the browser straight over to the live build.
3. If GitHub doesn't answer — internet down, GitHub down, connection
   hanging — the message changes to **"Loading Reference copy"** and it
   loads the snapshot kept on this server, saying what that copy is (and,
   once you set the date, how old it is).
4. A **"Use the local copy now"** button skips the wait at any moment.
   Adding `?local` to the loader's address does the same thing.
5. Any `?query` or `#hash` on the loader's address rides along to
   whichever copy wins.
6. With JavaScript off, the page simply shows both links and lets you pick.

Nothing is tracked, nothing is uploaded. The loader only points the
browser at one copy or the other.

The three loaders:

| Loader file (as delivered) | Site | Tries first (online) | Falls back to (sibling file) |
|---|---|---|---|
| `spectrum-search-loader_2026-11-24.html` | Spectrum Search | `https://caeled.github.io/mis-classmate-portal/SpectrumSearch.html` | `SpectrumSearch-reference.html` |
| `mis-portal-loader_2026-11-24.html` | MIS Portal | `https://caeled.github.io/mis-classmate-portal/` | `index-reference.html` |
| `everyday-cool-arcade-loader_2026-11-24.html` | Everyday Cool Arcade (Dad's Arcade) | `https://caeled.github.io/everyday-cool/arcade.html` | `arcade-reference.html` |

---

## Drop-in recipe — Spectrum Search

Work in the folder on PowellServer where `SpectrumSearch.html` lives now.

1. Rename the current `SpectrumSearch.html` to **`SpectrumSearch-reference.html`**.
   That file is now the reference copy.
2. Save `spectrum-search-loader_2026-11-24.html` into the same folder
   under the name **`SpectrumSearch.html`**.
3. Done. The old address now opens the loader; the loader opens the live
   build on GitHub, or the reference copy beside it when GitHub won't answer.

## Drop-in recipe — MIS Portal

Work in `/web/steve/phoenix/mis-portal-personal/` on PowellServer.

1. Rename the current `index.html` to **`index-reference.html`**.
2. Save `mis-portal-loader_2026-11-24.html` into the same folder under
   the name **`index.html`**.
3. Done — same behaviour: classmates' live portal first, your personal
   reference copy as the fallback.

## Drop-in recipe — Everyday Cool Arcade (Dad's Arcade)

Work in the folder on PowellServer where `arcade.html` lives now.

1. Rename the current `arcade.html` to **`arcade-reference.html`**.
2. Save `everyday-cool-arcade-loader_2026-11-24.html` into the same
   folder under the name **`arcade.html`**.
3. Done — live Arcade first, home reference copy when the internet is
   being unkind.

---

## Refreshing a reference copy later

Whenever a fresh server copy of a site is delivered (the usual AI-Delivery
Save-As):

1. Save it **over the `*-reference.html` name** — never over the loader's
   name. The loader stays put; only the snapshot changes.
2. Open the loader file (the one saved under the page's original name) in
   a text editor, find the **CONFIG** block at the top of the script, and
   set `LOCAL_DATE` to the refresh date, e.g. `LOCAL_DATE: "2026-12-01"`.
   The fallback message then reads "…Snapshot taken 2026-12-01." so a
   stale copy never pretends to be fresh.
3. While you're in CONFIG: `TIMEOUT_MS` is the 6-second wait, in
   milliseconds. Shorten or lengthen it there if the wait ever feels wrong.
