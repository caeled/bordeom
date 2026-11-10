# Bordeom — a collection of dumb, fun things

Small nostalgic programs: what a 1990s DOS toy looks like today. Each is one Python file, and each has a headless `--selftest`.

The very first program Steven ever wrote, in 7th grade, was a bouncing line. This collection is that instinct, kept.

## The programs

| Program | What it is | Needs |
|---|---|---|
| `warp.py` | Acidwarp tribute: palette-cycling psychedelic art (1990s DOS). Draws one picture of palette index numbers from a little maths, then rotates the palette every frame so the colours flow and nothing is redrawn. 9 pictures (rings, spiral, waves, plasma, kaleidoscope, interference, tunnel, warp, Julia set), 5 seamless palettes. | numpy, pygame |
| `bounce.py` | The bouncing line, in the spirit of the old DOS screen savers: two endpoints fly around and reflect off all four walls, and the line between them, with a fading trail, is the show. After a random wait the next bounce is special: a lone line splits into two to four that fan out, and when there are several, the line that just bounced dies (there is always at least one). A remake of Steven's seventh-grade first program. | numpy, pygame |
| `fractal.py` | Mandelbrot / Julia zoomer with colour cycling. Starts as a screen-saver "dive" into a spiral valley; click to take over and explore. A full 320x200 frame takes about 12 ms — it needed a maths coprocessor in the 1980s. | numpy, pygame |
| `morse.py` | Type text, press Go, hear it in Morse code. Hide-and-reveal for learning by ear, Farnsworth spacing, repeats, save-as-WAV. Made for Steven's father, a ham radio operator since 1956. Windows only (the beeps come from `winsound`). | numpy (tkinter is built in) |
| `surprise.py` | Pocket Orbit: a hypotrochoid curve drawn live, a new orbit on demand, saveable as SVG artwork. Pure standard library — nothing to install. Double-click `Surprise.cmd` on Windows, or run the file. | nothing |
| `sky.py` | Skywatch: what's up tonight, a backyard-telescope sky guide. The Sun, Moon and 8 planets from low-precision orbital elements, 95 deep-sky showpieces and 25 bright stars on an all-sky chart, with an "up now" list, rise/transit/set times, and a red night-vision mode that won't wreck your dark adaptation. Good enough for a finder scope, not for astrometry, and it says so. Set your site with `--lat` / `--lon`, plan ahead with `--at`. | numpy, pygame |

## Run them

```
pip install numpy pygame
python warp.py
python bounce.py
python fractal.py
python morse.py
python surprise.py
python sky.py
```

Common keys in warp and fractal: **Space** pause, **F / Enter** fullscreen, **S** screenshot, **H** hide/show help, **Esc / Q** quit. In Pocket Orbit: **Space** pause, **N** another orbit, **S** save, **Esc** close.

Every program verifies itself: `python warp.py --selftest` (and likewise for the others).

## MorseCode.exe — no Python needed

`MorseCode.exe` is `morse.py` packaged as one Windows file (about 23 MB, no install). It was built for the ham club. Windows may warn when you first run it (SmartScreen: **More info → Run anyway**) because it is unsigned — that warning appears for any small unsigned program.

## Notes

- `warp.py` options: `--hold 10` (seconds per picture), `--speed 60`, `--seed 42`, `--res 640x400` (default is the DOS 320x200, scaled up crisp).
- `fractal.py`: left click zooms in, right click out, wheel zooms at the cursor, arrows pan, **D** returns to dive mode, **J** shows the Julia set of the point under the mouse.
- `morse.py` timing is the real standard: dit = 1200/WPM ms, dah = 3 dits, gaps of 1/3/7 dits; PARIS plus its gap is exactly 50 dits, which is how WPM is defined.
