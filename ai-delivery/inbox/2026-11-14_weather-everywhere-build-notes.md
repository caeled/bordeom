# Build notes — Weather Everywhere, six new features
**Date:** 2026-11-14 · **Built from:** fresh clone of https://github.com/caeled/weather-everywhere (the October copy inside everyday-cool was *not* used) · **State:** working tree, uncommitted, nothing pushed or published.

## Audience note (steering, applied throughout)
Steven built this workshop for his son **Flynn (12)**, and it now runs on Flynn's **iPad**. Every new interaction was designed for that device first:
- **Tap only.** No hover-dependent behavior anywhere in the six features. Glossary meanings open by tap/click, never by mouse-over. A static audit confirms there are no `mouseover`/`mouseenter`/`mouseleave` handlers anywhere in `assets/app.js` (old or new code).
- **Generous targets.** All buttons in the new areas are at least 44px tall; glossary list rows are 52px+ with 16px padding; the date input is 44px tall; sliders are the app's existing full-width range inputs.
- **Touch-path smoke pass.** The jsdom suite drives every new feature the way a finger would: tap events for buttons and glossary words, value+input events for sliders — 44 checks, listed below.
- **Quiet skies honored.** No new feature animates, auto-plays, or fetches on its own. Sun & tilt and the glossary work fully offline; Look back and Opposite weather send a request only on an explicit tap, following the existing Look live pattern.

## What was built

### 1. What-if Earth knobs — new "Sun & tilt" room (rail item 07)
- **What-if tilt card:** place picker (the 16 built-in places) + tilt slider 0–45° with preset buttons (No tilt 0° · Earth today 23.5° · Tipped far over 45°). Output: twelve-month day-length curve on canvas, a chart-as-table, and a plain-words readout computed from the numbers (longest/shortest day and month; "the sun does not set/rise at all" months when they occur). At tilt 0 the readout states plainly that there are no seasons of light. A comparison line always shows the same place under Earth's real tilt.
- **Move your town card:** place picker + latitude slider (−90…90) with stop buttons (equator, its real latitude, the polar circle on its own side of the world, the pole on its own side). Only latitude changes; the town keeps its name. Same curve, table, and readout.
- Math lives in `assets/science.js`: `declination(day, tilt)` generalizes the existing mid-month approximation so obliquity is a variable, and `dayLength(lat, day, tilt)` applies the sunrise hour-angle formula with the same polar clamping as the existing `daylight()`. The existing `daylight()` is untouched; the Compare room behaves exactly as before. All output is labeled as computed teaching math.

### 2. Look back — weather on a past date (new card in the Map room)
- Date picker (1940 onward; the input's max is set to five days ago) + "Look back" button for the currently selected place or map pin. Fetches the Open-Meteo archive API (ERA5) for that single day: high, low, precipitation total, strongest wind.
- Honesty pattern matches Look live: status line names the source ("ERA5 reanalysis — a model reconstruction built from observations, not a thermometer reading at this exact spot"), the date, and the retrieval time. Too-recent dates are refused in plain words *before* any request ("the archive needs about five days…"). A day the archive returns no values for gets a plain no-data message. Values are never invented. Results can be saved to the notebook, like forecasts.
- Cache: in-memory, per place + date, for the session only (per the brief — deliberately *not* localStorage, so no stale past-day data survives a restart).

### 3. Opposite weather (new card in the Map room)
- Two buttons: **antipode** (latitude reversed, longitude shifted 180°) and **mirror latitude** (latitude reversed, same longitude). One tap fetches current Open-Meteo conditions for the selected place and the opposite point; two cards render side by side.
- The opposite point is labeled honestly: "Near *place*" only if it lies within 250 km (haversine) of a built-in place; otherwise "Land, far from the workshop's named places" or "Open ocean", always with its coordinates. Land/ocean is decided by an even-odd point-in-polygon test against the bundled Natural Earth polygons. The point is never moved to a nearer city. The card copy says up front that most of Earth is water, so the opposite is usually ocean weather.

### 4. Sun slider — daylight explorer (third card in the Sun & tilt room)
- Place picker + day-of-year slider (1–365) with a date readout. Shows sunrise, sunset, and day length as big metrics, plus a comparison line with today's real day length at that place. Edge cases are stated in words: "the sun does not set" / "the sun does not rise… apart from twilight, which this simple model leaves out."
- Times are **local solar time** (sun highest at noon), computed as 12 ∓ dayLength/2 by `sunTimes()` in science.js. The card and SCIENCE.md both say this is close to clock time but uses no time zones or equation-of-time correction. Pure math, fully offline.

### 5. Plain-words weather words — glossary (`assets/glossary.js`, new file; rail item 08 "Weather words")
- 32 terms the workshop itself uses (dew point, front, reanalysis, solstice, Beaufort scale, …), each with a one-to-two-sentence plain-language meaning written for this project. No external dictionary text.
- Two ways in: a **Words room** listing every term as a large tappable row (tap opens the meaning, tap again closes it), and **inline annotation** — in Look live output, Look back results, Opposite results, and the Sun room readouts, glossary terms become dotted-underlined tap targets; tapping one opens its meaning in place, tapping again closes it. Annotation never touches links, buttons, inputs, or the notes it creates, and never navigates anywhere.

### 6. Wind in human terms — Beaufort scale
- `beaufort(kmh)` in science.js (tested pure function) returns the WMO Beaufort number, name, and a plain description ("Small trees sway…"). It now appears next to the wind speed in Look live, in Look back results, and on both Opposite cards. Beaufort itself is unit-free; the numeric speed stays in km/h exactly as the provider delivers it, as before.

## Documentation
- **SCIENCE.md** (+3,873 bytes): new sections for the variable-tilt declination and hour-angle formulas and their limits, the ERA5 archive (provenance, 1940 start, ~5-day lag, session-only cache), opposite-point math and the 250 km naming rule, the full Beaufort band table, and the glossary's authorship.
- **README.md** (+1,249 bytes): four new Explore bullets (Look back, Opposite weather, Sun & tilt, Weather words) and a Beaufort sentence added to the Look live bullet.

## Verification (all run 2026-11-14, all green)
- `node --test tests/science.test.cjs` — **21/21 pass** (11 original, untouched and still green, + 10 new): declination at both solstices; day length ≈ 12 h at tilt 0 across nine latitudes and five days, poles included; London on day 172 at 23.44° = 16.41 h against a value hand-computed from the same formula before coding; tilt ordering (45° winter < 23.44° winter < 0° = exactly 12); sunrise/sunset symmetry about solar noon; Tromsø polar day/night via `sunTimes`; antipode and mirror math (including round-trip and the antipodal distance ≈ half Earth's circumference); all Beaufort boundaries from the brief (1, 19, 29, 39, 50, 62, 75, 89, 103, 118 km/h) plus names, descriptions, and NaN/negative handling; glossary presence, shape, and lookup for 14 required terms.
- `python tests/check-package.py` — **pass**: 107 unique IDs, 29 links/assets resolve (including the new glossary script).
- **jsdom smoke pass — 44/44 checks** (page loaded from disk with canvas, matchMedia, and fetch stubbed): zero page errors on load and at the end; all eight rooms render; original features intact (place card, 12-row season table, nine missions). Per feature: glossary rows open/close by tap; Look live output gains Beaufort words and a tappable "humidity" whose meaning opens and closes in place; tilt 0 readout text and 12.0-hour days; Tromsø "does not set"; preset and stop buttons work by tap; sun slider polar day/night messages and the dash for absent sunrise; Look back fires exactly one archive fetch, only on tap, with the correct URL (selected coordinates, the chosen date as start and end, the four daily variables) and renders the stubbed day with its ERA5 label and Beaufort words; a too-recent date is refused with no fetch; the antipode tap fetches both true opposite coordinates (67.57, 111.87 for Rothera) and renders two honestly labeled cards with coordinates; the mirror tap keeps longitude and reverses latitude; static audit confirms no hover handlers exist.
- Land/ocean point-in-polygon spot-checked against known geography: Siberia → land, Indian Ocean → ocean, near New Zealand → land, Sumatra → land.

## Honest partials and limits
- **Sunrise/sunset are solar-time approximations**, not clock times; they can differ from published tables by tens of minutes (no time zones, no equation of time, no twilight). Labeled in the UI and in SCIENCE.md.
- **Coastline classification is approximate**: the bundled Natural Earth data is 1:110m, so a point very close to a coast can be called land or ocean either way. Labeled in SCIENCE.md.
- **Charts were not pixel-verified**: the smoke pass ran the new canvas charts against a no-op 2D context (jsdom has no canvas). The charts use the same `chart()` helper the Compare room already ships with, and every chart's values are also printed as a table and in the readout text, so no information depends on the pixels.
- The tilt preset labeled "Earth today" sets 23.5° (the rounded value used in the app's prose) while the internal constant is 23.44°; the difference is under 0.05 hours of day length everywhere and is documented in SCIENCE.md.
- Glossary annotation is applied to live/past-day/opposite outputs and the Sun room readouts — the places a reader meets the words mid-task — not to every static paragraph in the workshop.

## Files changed (+38,789 bytes total)
| File | Change | Size |
|---|---|---|
| `assets/science.js` | + `declination`, `dayLength`, `sunTimes`, `antipode`, `mirrorPoint`, `haversineKm`, `beaufort`; existing functions byte-identical | 1,479 → 3,626 |
| `assets/glossary.js` | **new**: 32 plain-language definitions + lookup, deferred script in the existing pattern | 4,869 (new) |
| `assets/app.js` | wiring only at five existing points (room list, units re-render, place-change reset, Look live line, init) + one inserted block: glossary annotation, Words room, Look back, Opposite weather, Sun & tilt | 28,950 → 45,193 |
| `index.html` | glossary script tag, two rail links, Look back + Opposite cards in the Map room, new Sun & tilt and Weather words sections | 14,823 → 20,937 |
| `assets/style.css` | appended rules only: tappable words, meaning notes, word rows, 44px targets in new areas | 9,158 → 9,977 |
| `SCIENCE.md` | five new sections (above) | 4,778 → 8,651 |
| `README.md` | four Explore bullets + one sentence in the Look live bullet | 5,082 → 6,331 |
| `tests/science.test.cjs` | 10 new tests appended; original 11 untouched | 2,658 → 6,143 |

Untouched, as required: `assets/land.js`, `assets/places.js`, `assets/snapshots.js`, the notebook storage format, and every existing feature's behavior.
