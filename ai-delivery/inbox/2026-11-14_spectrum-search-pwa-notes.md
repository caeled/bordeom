# Spectrum Search — Chromebook (PWA) package, v0.8.1 — Nov 14, 2026

## What this is
The pieces that make Spectrum Search an installable app on a Chromebook
(the same mechanism installs it on any Chrome browser, Windows/Mac/Android too).
Installed, it sits in the Chromebook launcher like a native app, opens in its
own window with no browser bars, and opens fast. This is a PWA (Progressive
Web App): no app store, no developer account, no review process.

## Files (all four go in the SAME folder as each other)
- SpectrumSearch.html — v0.8 with exactly three additions, nothing else changed:
  a theme-color line, a manifest link, and a short service-worker registration
  script at the end. On browsers that can't register it, the page behaves
  exactly like v0.8.
- manifest.json — the install card: name, description, colors, icons.
- sw.js — the service worker. It caches ONLY the app shell (the page, the
  manifest, the icons) so an installed copy opens offline. Search requests are
  never cached and never intercepted; they go to the network exactly as the
  page sends them, and results stay live.
- icons/icon-192.png, icons/icon-512.png — magnifier over plain text lines,
  in the page's own colors (paper #f7f5f0, teal #2f6f6a, ink #1c2430).

## The one catch, stated plainly
Chrome only offers "Install" from an HTTPS page. PowellServer is plain HTTP,
so on the server copy the page works exactly as it does today, but the Install
button will not appear there. The GitHub Pages copy IS HTTPS, so install works
from there — but that copy is still v0.6. Two ways to a working Chromebook
install:
1. Update the GitHub Pages copy to this package (Muse can do it on your word).
2. Put HTTPS on PowellServer (bigger job, your server, your call).
Deploying this package to PowellServer anyway is harmless and future-proof:
the moment the server gets HTTPS, install switches on with no further changes.

## School Chromebooks
On a personal Chromebook, install is the student's choice. On school-managed
Chromebooks, the school's admin policy decides whether installs are allowed;
some block them. The plain web page needs no install and works either way,
which is the floor this was designed to: the page first, the install as a bonus.

## Deploy (server)
Save-As SpectrumSearch.html over the server copy; put manifest.json and sw.js
beside it in the phoenix folder, and the icons folder under it
(phoenix/icons/icon-192.png, phoenix/icons/icon-512.png). Relative paths
throughout, so the folder can live anywhere.

## Verified
manifest.json parses; sw.js passes node --check; the HTML diff against v0.8
is only the three additions listed above (262,458 bytes vs 261,950).
Not yet done: a live install test on a real Chromebook (none on hand here).
The first student who taps Install is the real test — breakage is the audit.
