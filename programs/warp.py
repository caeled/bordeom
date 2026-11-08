"""Bordeom / warp.py -- a tribute to Acidwarp, the classic DOS "psychedelic screen saver".

The trick, then and now: draw ONE picture of index numbers 0-255 from a little maths (rings, spirals,
waves...), then *rotate the palette* every frame. The colours flow through the shapes and nothing is
redrawn. Every so often: fade to black, new picture, new palette, fade in.

    python warp.py                 # play (Esc or Q quits)
    python warp.py --hold 10       # 10 seconds per picture
    python warp.py --seed 42       # same first picture every time
    python warp.py --selftest      # headless checks, no window

Keys:  N or Right = next picture     P = new palette     Up/Down = speed     R = reverse
       Space = pause     F or Enter = fullscreen     S = save a screenshot     H = hide/show help
"""

import argparse
import math
import os
import random
import sys
import time

import numpy as np

TWO_PI = 2 * math.pi
HERE = os.path.dirname(os.path.abspath(__file__))


# -- The picture: a grid of coordinates, and generators that return a value per pixel ------------------
class Grid:
    """Pixel coordinates centred on the screen, in 'classic 320x200' units whatever the real size."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        s = 320.0 / w
        py, px = np.mgrid[0:h, 0:w].astype(np.float32)
        self.x = (px - w / 2) * s
        self.y = (py - h / 2) * s
        self.r = np.hypot(self.x, self.y)
        self.t = np.arctan2(self.y, self.x)  # -pi .. pi


def to_index(v: np.ndarray) -> np.ndarray:
    """Any float array -> palette indexes 0..255 (wraps around, so bands repeat)."""
    return (np.floor(np.nan_to_num(v)).astype(np.int64) % 256).astype(np.uint8)


def norm(v: np.ndarray, bands: float) -> np.ndarray:
    """Stretch to 0..1, then to `bands` full trips round the palette."""
    lo, hi = float(v.min()), float(v.max())
    return (v - lo) / (hi - lo + 1e-9) * 256.0 * bands


def rings(rng, g):
    cx, cy = rng.uniform(-80, 80), rng.uniform(-50, 50)
    return np.hypot(g.x - cx, g.y - cy) * rng.uniform(1.0, 6.0)


def spiral(rng, g):
    arms = rng.randint(1, 7) * rng.choice([-1, 1])
    return g.r * rng.uniform(0.5, 4.0) + g.t / TWO_PI * 256.0 * arms  # whole turns only: no seam


def waves(rng, g):
    v = 0
    for _ in range(rng.randint(2, 4)):
        a, f, ph = rng.uniform(0, TWO_PI), rng.uniform(0.02, 0.12), rng.uniform(0, TWO_PI)
        v = v + np.sin((g.x * math.cos(a) + g.y * math.sin(a)) * f + ph)
    return norm(v, rng.uniform(1, 4))


def plasma(rng, g):
    a, b, c, d = (rng.uniform(0.02, 0.09) for _ in range(4))
    v = (np.sin(g.x * a + rng.uniform(0, 6)) + np.sin(g.y * b + rng.uniform(0, 6))
         + np.sin((g.x + g.y) * c) + np.sin(g.r * d))
    return norm(v, rng.uniform(1.5, 5))


def kaleido(rng, g):
    n = rng.randint(3, 12)
    t = np.abs(np.mod(g.t, TWO_PI / n) - math.pi / n)  # fold the angle into one wedge
    return g.r * rng.uniform(0.6, 3.0) + np.sin(t * rng.randint(2, 9) * n) * rng.uniform(10, 60) \
        + t * rng.uniform(20, 120)


def interference(rng, g):
    pts = [(rng.uniform(-120, 120), rng.uniform(-70, 70)) for _ in range(rng.randint(2, 3))]
    d = [np.hypot(g.x - x, g.y - y) for x, y in pts]
    mode = rng.choice(["sum", "diff", "prod"])
    v = d[0] + d[1] if mode == "sum" else d[0] - d[1] if mode == "diff" else d[0] * d[1] / 60.0
    if len(d) == 3:
        v = v + d[2] * rng.choice([-1, 1])
    return v * rng.uniform(0.8, 3.0)


def tunnel(rng, g):
    return 3000.0 / (g.r + 8.0) * rng.uniform(0.6, 2.0) + g.t / TWO_PI * 256.0 * rng.randint(1, 4)


def warp(rng, g):
    return g.x * rng.uniform(0.5, 3) + np.sin(g.y * rng.uniform(0.02, 0.12)) * rng.uniform(20, 90) \
        + np.sin(g.x * rng.uniform(0.02, 0.09)) * rng.uniform(10, 60)


JULIA_C = [-0.8 + 0.156j, -0.4 + 0.6j, 0.285 + 0.01j, -0.70176 - 0.3842j, -0.835 - 0.2321j, 0.37 + 0.1j,
           -0.123 + 0.745j, -0.75 + 0.11j]


def julia(rng, g):
    c = rng.choice(JULIA_C) + complex(rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02))
    z = ((g.x + 1j * g.y) / (100.0 * rng.uniform(1.0, 2.0))).astype(np.complex64)
    n = np.zeros(z.shape, np.float32)
    alive = np.ones(z.shape, bool)
    for i in range(48):
        z[alive] = z[alive] * z[alive] + c
        esc = alive & (np.abs(z) > 2)
        n[esc] = i + 1 - np.log2(np.log2(np.abs(z[esc])))  # smooth colouring
        alive &= ~esc
    return n * rng.uniform(4, 14)


PATTERNS = [("RINGS", rings), ("SPIRAL", spiral), ("WAVES", waves), ("PLASMA", plasma),
            ("KALEIDO", kaleido), ("INTERFERENCE", interference), ("TUNNEL", tunnel),
            ("WARP", warp), ("JULIA", julia)]


# -- The colours: 256 entries that loop round seamlessly, so rotating them never shows a join ---------
def pal_cosine(rng):
    t = (np.arange(256) / 256.0)[:, None]
    a = np.array([rng.uniform(0.35, 0.65) for _ in range(3)])
    b = np.array([rng.uniform(0.3, 0.5) for _ in range(3)])
    c = np.array([rng.choice([1, 1, 2, 3]) for _ in range(3)])  # whole numbers: colour repeats exactly
    d = np.array([rng.random() for _ in range(3)])
    return (np.clip(a + b * np.cos(TWO_PI * (c * t + d)), 0, 1) * 255).astype(np.uint8)


def pal_rainbow(rng):
    t = (np.arange(256) / 256.0)[:, None]
    d = np.array([0.0, 1 / 3, 2 / 3]) + rng.random()
    return (np.clip(0.5 + 0.5 * np.cos(TWO_PI * (t + d)), 0, 1) * 255).astype(np.uint8)


def pal_fire(rng):
    u = 1 - np.abs(2 * np.arange(256) / 256.0 - 1)  # up then back down
    rgb = np.stack([np.clip(u * 3, 0, 1), np.clip(u * 3 - 1, 0, 1), np.clip(u * 3 - 2, 0, 1)], axis=1)
    if rng.random() < 0.5:
        rgb = rgb[:, ::-1]  # "blue fire"
    return (rgb * 255).astype(np.uint8)


def pal_duotone(rng):
    c1 = np.array([rng.random() for _ in range(3)])
    c2 = np.array([rng.random() for _ in range(3)])
    u = ((1 - np.cos(TWO_PI * rng.choice([1, 2, 3, 4]) * np.arange(256) / 256.0)) / 2)[:, None]
    return ((c1 + (c2 - c1) * u) * 255).astype(np.uint8)


def pal_banded(rng):
    base = pal_cosine(rng)
    w = rng.choice([8, 16, 32])
    return base[(np.arange(256) // w) * w]  # hard stripes, very 1993


PALETTES = [("COSINE", pal_cosine), ("RAINBOW", pal_rainbow), ("FIRE", pal_fire),
            ("DUOTONE", pal_duotone), ("BANDED", pal_banded)]
SMOOTH = {"COSINE", "RAINBOW", "FIRE", "DUOTONE"}  # every step to the next entry (and the wrap) is small


# -- The show ----------------------------------------------------------------------------------------
def selftest() -> int:
    rng = random.Random(1234)
    g = Grid(320, 200)
    bad = 0

    def check(ok, what):
        nonlocal bad
        print(("PASS " if ok else "FAIL ") + what)
        bad += (not ok)

    for name, fn in PATTERNS:
        idx = to_index(fn(rng, g))
        check(idx.shape == (200, 320) and idx.dtype == np.uint8 and len(np.unique(idx)) > 8,
              f"pattern {name}: 320x200 uint8, {len(np.unique(idx))} distinct indexes")
    for name, fn in PALETTES:
        pal = fn(rng)
        ok = pal.shape == (256, 3) and pal.dtype == np.uint8
        if name in SMOOTH:
            step = np.abs(np.diff(np.vstack([pal, pal[:1]]).astype(int), axis=0)).max()  # includes the wrap
            ok = ok and step < 60
            check(ok, f"palette {name}: 256x3, loops seamlessly (biggest step {step})")
        else:
            check(ok, f"palette {name}: 256x3")
    a, b = to_index(rings(random.Random(7), g)), to_index(rings(random.Random(7), g))
    check(bool((a == b).all()), "same seed gives the same picture")
    print("ALL PASSED" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Acidwarp-style palette-cycling art")
    ap.add_argument("--res", default="320x200", help="drawing size, default 320x200 (the DOS mode)")
    ap.add_argument("--hold", type=float, default=20.0, help="seconds each picture stays")
    ap.add_argument("--speed", type=float, default=40.0, help="palette colours per second")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    import pygame  # only needed for the window, so the self-test runs without it

    w, h = (int(n) for n in args.res.lower().split("x"))
    rng = random.Random(args.seed if args.seed is not None else time.time_ns())
    grid = Grid(w, h)

    pygame.init()
    screen = pygame.display.set_mode((w, h), pygame.SCALED | pygame.RESIZABLE)  # crisp pixels, any size
    pygame.display.set_caption("Bordeom - warp")
    canvas = pygame.Surface((w, h))
    font = pygame.font.Font(None, 16)
    clock = pygame.time.Clock()

    state = {"idx": None, "pal": None, "prev_pal": None, "mix": 1.0, "name": "", "pal_name": "",
             "last": -1}

    def new_picture():
        choices = [i for i in range(len(PATTERNS)) if i != state["last"]]
        state["last"] = rng.choice(choices)
        state["name"], fn = PATTERNS[state["last"]]
        state["idx"] = to_index(fn(rng, grid))
        new_palette(instant=True)

    def new_palette(instant=False):
        state["prev_pal"] = None if instant else state["pal"]
        state["mix"] = 1.0 if instant else 0.0
        state["pal_name"], pf = rng.choice(PALETTES)
        state["pal"] = pf(rng)

    new_picture()
    offset, speed, paused, help_on = 0.0, args.speed, False, True
    fade = 1.2
    phase, t_phase, label_until = "in", 0.0, time.time() + 3.0
    running = True

    def leave():  # start fading out, keeping the brightness continuous
        nonlocal phase, t_phase
        if phase != "out":
            b = min(1.0, t_phase / fade) if phase == "in" else 1.0
            phase, t_phase = "out", (1.0 - b) * fade

    while running:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif k in (pygame.K_n, pygame.K_RIGHT):
                    leave()
                elif k == pygame.K_p:
                    new_palette()
                elif k == pygame.K_UP:
                    speed = math.copysign(min(300.0, max(2.0, abs(speed) * 1.25)), speed)
                elif k == pygame.K_DOWN:
                    speed = math.copysign(max(2.0, abs(speed) / 1.25), speed)
                elif k == pygame.K_r:
                    speed = -speed
                elif k == pygame.K_SPACE:
                    paused = not paused
                elif k in (pygame.K_f, pygame.K_RETURN):
                    try:
                        pygame.display.toggle_fullscreen()
                    except pygame.error:  # e.g. a display driver that can't go fullscreen
                        pass
                elif k == pygame.K_h:
                    help_on = not help_on
                elif k == pygame.K_s:
                    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
                    path = os.path.join(HERE, "shots", time.strftime("warp-%Y%m%d-%H%M%S.png"))
                    pygame.image.save(pygame.transform.scale(canvas, (w * 3, h * 3)), path)
                    label_until, state["name"] = time.time() + 2.0, "SAVED " + os.path.basename(path)

        if not paused:
            offset = (offset + speed * dt) % 256.0
        t_phase += dt
        if phase == "in":
            bright = min(1.0, t_phase / fade)
            if t_phase >= fade:
                phase, t_phase = "hold", 0.0
        elif phase == "hold":
            bright = 1.0
            if t_phase >= args.hold:
                leave()
        else:
            bright = max(0.0, 1.0 - t_phase / fade)
            if t_phase >= fade:
                new_picture()
                phase, t_phase, label_until = "in", 0.0, time.time() + 3.0
                bright = 0.0

        if state["prev_pal"] is not None:  # crossfade to a new palette over a second
            state["mix"] = min(1.0, state["mix"] + dt)
            pal = state["prev_pal"] * (1 - state["mix"]) + state["pal"] * state["mix"]
            if state["mix"] >= 1.0:
                state["prev_pal"] = None
        else:
            pal = state["pal"]
        rgb = (np.roll(pal, int(offset), axis=0).astype(np.float32) * bright).astype(np.uint8)
        pygame.surfarray.blit_array(canvas, np.ascontiguousarray(rgb[state["idx"]].swapaxes(0, 1)))

        lines = []
        if time.time() < label_until:
            lines.append(f"{state['name']}  /  {state['pal_name']}")
        if help_on:
            lines += ["N next  P palette  R reverse  Up/Down speed", "Space pause  F fullscreen  S shot  H help  Q quit"]
        for n, text in enumerate(lines):
            for dx, dy, col in ((1, 1, (0, 0, 0)), (0, 0, (255, 255, 255))):
                canvas.blit(font.render(text, False, col), (4 + dx, h - 12 * (len(lines) - n) - 2 + dy))
        screen.blit(canvas, (0, 0))
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
