# Bordeom -- a collection of dumb, fun things

Small nostalgic programs. Python + numpy + pygame. Each is one file; each has a headless `--selftest`.

```
pip install -r requirements.txt
python warp.py        # Acidwarp tribute
python bounce.py      # the bouncing line
python fractal.py     # the endless spirals (Mandelbrot / Julia zoomer)
python morse.py       # type something, hear it in Morse code (Windows)
```

| Program | What it is |
|---|---|
| `warp.py` | Acidwarp tribute: palette-cycling psychedelic art (1990s DOS). |
| `bounce.py` | A line bouncing off all four walls; at random it splits into several, or one dies. |
| `fractal.py` | Mandelbrot / Julia zoomer with Acidwarp colour cycling. Starts as a screen-saver "dive", click to explore. |
| `morse.py` | Type text, press Go, hear it in Morse code. Made for Steve's father, a ham radio operator since 1956. |

Common keys: **Space** pause, **F / Enter** fullscreen, **S** screenshot (to `shots\`), **H** hide/show help, **Esc / Q** quit.

## Spark

*A dumb idea Steve had in his head all day (2026-09-19). Purely nostalgic: what would a 1990s DOS toy look like now?
And: the very first program he ever wrote, in 7th grade, was a bouncing line.*

---

## warp.py -- Acidwarp tribute

Written from scratch (no code from the original). **The trick, then and now:** draw one picture made of palette *index
numbers* 0-255 from a little maths, then **rotate the palette** every frame. The colours flow through the shapes and
nothing is redrawn. Every ~20 seconds: fade to black, new picture, new palette, fade in.

Options: `--hold 10` (seconds per picture), `--speed 60` (palette colours per second), `--seed 42` (repeatable),
`--res 640x400` (drawing size; default is the DOS 320x200, scaled up with crisp pixels), `--selftest`.
Keys: **N / Right** next picture, **P** new palette, **Up / Down** speed, **R** reverse.

- **9 pictures** (`PATTERNS`): rings, spiral, waves, plasma, kaleidoscope, interference, tunnel, warp, Julia set. Each
  returns a float per pixel; `to_index` wraps it to 0-255, so bands repeat. Add one: write `f(rng, grid)`, add it to the list.
- **5 palette kinds** (`PALETTES`): cosine, rainbow, fire, duotone, hard-banded. All 256 entries loop round *seamlessly*
  (the self-test checks the biggest colour step, wrap-around included), so rotating never shows a join.
- Drawing is done once per picture; each frame only re-colours (`palette[index_image]`) and scales up.

## bounce.py -- the bouncing line

Two endpoints fly around and reflect off **all four walls**; the line between them, with a fading colour trail (Mystify
style), is the show. After a **random period** (default 3-9 s, `--period MIN MAX`) the **next bounce** is special:

- only **one** line -> it **splits** into 2-4 lines that fan out (children copy the parent's position, velocity turned
  12-70 degrees, same speed);
- **several** lines -> the line that just bounced **dies** (its trail drains away). The count never reaches zero.

Options: `--speed 220` (pixels/s), `--trail 36` (frames), `--res 640x400`, `--seed 42` (repeatable), `--rhythm`, `--selftest`.
Keys: **Up / Down** speed, **R** restart, **T** switch rhythm live.

- **Rhythm** (how the random wait is drawn): `flat` (even random 3-9 s, mean 6.0; **no longer the default**, see the Easter egg below), `nested` (Steve's old BASIC trick
  `INT(RND(1)*(INT(RND(1)*N)+1))+1`: one draw sets the ceiling for the next, so mostly short waits with the odd long one;
  in continuous form the wait is min + range*u1*u2, mean 4.5) and `deep` (three deep, mean 3.75, bursts and rare pauses).
  Simulated for N=10 the nested idiom gives 29% / 19% / 14% ... 1% for the values 1..10 instead of 10% each.

- **Easter egg (Steve's idea, 2026-09-20; nothing on screen or in `--help` mentions it):** with no `--rhythm`, the default is not random. Each weekday
  keys its own letter in Morse through the split/kill events: **M T W R F S U** for Monday..Sunday (the course-timetable letters, so
  Tuesday/Thursday and Saturday/Sunday differ). Waits between special bounces: dot = 1 unit, dash = 3 units, the letter's last wait
  +6 units (letter space), then it repeats; unit = (min+max)/12 = 1 s at the default 3-9 s, so it scales with `--period`.
  Monday `--` = 3, 9 s; Tuesday `-` = 9 s; Wednesday `.--` = 1, 3, 9; Thursday `.-.` = 1, 3, 7; Friday `..-.` = 1, 1, 3, 7; Saturday `...` = 1, 1, 7;
  Sunday `..-` = 1, 1, 9. An event fires on the first wall hit after its wait, so the rhythm is blurred by up to a second or two;
  the self-test proves events are never early and the letters decode back exactly. It reads the **computer's clock, no time server**, so a wrong
  clock keys the wrong day. The HUD calls it `default`; `T` steps default -> flat -> nested -> deep. Test aid: `--day 0..6` (hidden). Code: `day_pattern()` in `bounce.py`.
- **Randomizer:** NumPy's PCG64 (`np.random.default_rng`), seeded from the operating system's entropy unless `--seed`
  is given. Directions are re-drawn until neither axis is near zero, so a line can't get stuck shuttling between two walls.
- **Bounces are exact:** `reflect()` unfolds the path (a wall is a mirror) so even a step that crosses the screen twice folds
  back correctly. Speed is never changed by a bounce. The self-test checks: positions always on screen over 60000 steps
  (some huge), speeds unchanged, all four walls hit, the split/kill rule (a split only from one line, a kill only from
  several), line count always 1-4, dead trails drain, same seed repeats.
- The physics (`Sim`) has no pygame in it, so it is tested without a window.

## fractal.py -- the endless spirals

The Mandelbrot set and its Julia cousins. In the 1980s a picture like this took minutes to hours and wanted a maths
coprocessor; here the classic 320x200 view takes about 12 ms. Starts in **dive** mode (falls into a spiral valley at
`--rate` doublings per second, holds, fades, next target); **click** to take over.

Mouse: left click zoom in, right click zoom out, wheel zoom at the cursor. Keys: **arrows** pan, **PageUp/PageDown**
zoom, **D** dive mode, **J** Julia set of the point under the mouse (again to go back), **P** palette, **[ ]** colour
speed, **- / +** fewer/more iterations, **R** reset. Options: `--manual` (start in explore mode), `--res 640x400`.

- **How it draws:** `compute()` iterates z = z*z + c for the whole picture at once, dropping pixels as they escape (the
  cost follows the detailed pixels), skips the main cardioid and the period-2 bulb (known inside), and uses a big bailout
  radius plus `log2(log2|z|)` for smooth colour bands. The picture is one index image; colours cycle like `warp.py`.
- **The targets were found by computation, not memory:** several remembered coordinates went flat by zoom 1e-9, so each
  candidate was refined by repeatedly zooming toward the most detailed pixel; the self-test checks all six stay rich
  in detail at 1e-9. Iterations grow with depth (`max_iter_for`, capped at 4000). Precision floor is 1e-13 per pixel
  (float64 runs out of digits below that); the dive stops at 2e-11.
- **Keeps moving when deep:** if a frame takes over 300 ms during a dive it draws at half size until it is cheap again.
- Self-test: known points in and out of the set, the Julia c=0 disk, mirror symmetry about the real axis, the targets, the
  iteration budget.

## morse.py -- Morse code for Dad

A small window (tkinter, nothing to install; Windows only, it uses `winsound`): type in the box, press **Go** (or Ctrl+Enter),
hear it; **Stop** cuts it off (within 0.05 s, even in a long gap). The dots and dashes are shown under the box.

**Learning aids (added the same night, for training the ear):**
- **Hide dots and dashes** (tick box) keeps the visual answer away while it plays; **Reveal** shows it afterwards.
- **Repeats** (0 = until Stop): the message loops, with a pause of three word gaps between repeats.
- **Farnsworth spacing:** *Letter speed* is how fast each letter is sent; *Overall* (blank = same) is the speed of the whole
  message. Below the letter speed it stretches only the gaps between letters and words, so every letter still sounds like
  real Morse. Formula: one spacing unit = (60/overall - 37.2/letters) / 19 seconds; 3 units between letters, 7 between words.
- **Save WAV...** writes what you typed, with all of the above, to a standard WAV (44.1 kHz, mono, 16-bit, 5 ms fades so no
  clicks). **Export at least (seconds)** repeats whole messages until the file is that long (capped at 30 minutes); otherwise
  it uses Repeats.

Options: `--wpm`, `--fwpm`, `--hz`, `--loops`, `--save FILE.wav`, `--seconds`. Examples: `python morse.py "CQ CQ" --wpm 15`,
`python morse.py "73" --save 73.wav`, `python morse.py "CQ" --wpm 20 --fwpm 8 --loops 0` (until Ctrl+C),
`python morse.py "CQ" --save cq.wav --seconds 300` (fills at least five minutes).

- **Standard timing:** dit = 1200/WPM ms; dah = 3 dits; gap 1 dit inside a letter, 3 between letters, 7 between words. PARIS plus
  its gap is exactly 50 dits, which is how WPM is defined. Every element is scheduled against the clock, not by adding delays,
  because each Windows `Beep` call has a few ms of overhead (the first version was 6% slow).
- All 26 letters, 10 digits and common punctuation. Characters with no code are skipped.
- **Checks:** `--selftest` has 19 checks (code table, timing, Farnsworth against the 60/overall definition, WAV format, length
  and tone count, loops, export-length rule, cap). The window's Go / Hide / Reveal / Save / Repeats / Stop were driven by a
  script and matched hand-calculated lengths. Played through speakers and timed: 2 loops of SOS (25 letters / 10 overall)
  took 9.87 s vs 9.85 s expected.
- **Exe (for the ham club):** `dist/MorseCode.exe`, one file, about 23 MB, no install and no Python needed, Windows only. Built with
  `python -m PyInstaller --onefile --windowed --name MorseCode --distpath dist --workpath _build --specpath _build --exclude-module pygame
  --exclude-module matplotlib --exclude-module scipy --exclude-module PIL --exclude-module pandas morse.py` (the work and spec folders must
  be on the same drive as the script; delete `_build` afterwards). Tested through the exe itself: `--selftest` exits 0, `--save` writes a WAV
  (so numpy is packed in), the window opens and stays responsive. `--windowed` means no console, so the command-line options work but print
  nothing. **Windows may warn** (SmartScreen: More info > Run anyway; some antivirus flags any PyInstaller exe) because it is unsigned. Give
  people only `MorseCode.exe`, not this folder (`DearDad.zip` is personal).
- **Ideas:** a decoder (`--decode file.wav`: read the tones back into text, the way the first check of Steve's WAV was done),
  random practice groups / Koch method (learn a few characters at a time), prosigns (AR, SK), a light that flashes with
  the tone.

## Where I left off (update this when you stop)

*2026-10-11: Added a local surprise from the request in the chat "Access Revocation Warning".
Double-click `Surprise.cmd` to reveal it, or run `python surprise.py`. No extra packages required.
`python surprise.py --selftest` runs the automated checks. Headless export and all four existing
program self-tests passed. A hidden real-window smoke test also passed: drawing, pause/resume,
resize, reset, save, cancel, and close. Live appearance still awaits the reveal.*

*Last updated 2026-09-19.*

- **Done:** `warp.py` (15 self-test checks), `bounce.py` (17), `fractal.py` (12) and `morse.py` (19) written and passing; frames rendered and
  looked at; all windows ran without crashing; `fractal.py`'s keys and mouse were driven by a scripted headless session
  (no exceptions). Fullscreen toggles are wrapped so a display that cannot do fullscreen does not crash them.
- **Not yet checked by a human:** the live feel of each (speed, fade length, help text size), fullscreen, screenshot key.
- **Next:** Steve said "two more": bounce and fractal are those two. His old BASIC trick `INT(RND(1)*(INT(RND(1)*N)+1))+1`
  is now `bounce.py --rhythm nested` (T switches live). **Settled 2026-09-20:** the default is the weekday Morse letter (Easter egg above);
  flat/nested/deep remain via `--rhythm` and T.
- **Idea from Steve (2026-09-20), to chat about:** a small stand-alone tool, `folder2pdf`: take a folder and produce one PDF from the documents inside it. The email downloader's isolated PDF writer (`email_downloader/python/pdf_export.py`, `export_batch_pdf(entries, path, title)` taking (name, text) pairs) is the starting point; text files work as they are, other formats (docx, html) would need a text-extraction step first.
- **Ideas:** fractal: Julia dive mode, a Burning Ship / Newton set, higher-res 'still' renders, a smoother zoom by
  reusing the previous frame. warp: dissolve transitions, more pictures (moire, rose curves, Mandelbrot zoom), a Windows `.scr` wrapper.
  bounce: bounce sparks, a "no trail" clean-line mode, sound blips on bounce. Both: a C# port for a single exe (the
  email downloader's exe recipe works).
- **To resume cold:** `python warp.py --selftest`, `python bounce.py --selftest`, `python fractal.py --selftest` and
  `python morse.py --selftest`, then run them.
