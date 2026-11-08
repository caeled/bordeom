"""Bordeom / fractal.py -- the endless spirals: a Mandelbrot / Julia zoomer with Acidwarp-style colour cycling.

In the 1980s a picture like this took minutes to hours and wanted a maths coprocessor. Here the classic
320x200 view takes ~13 ms. It starts in "dive" mode (a screen saver that falls into a spiral valley and keeps
going); click anywhere to take over and explore.

    python fractal.py               # play (Esc or Q quits)
    python fractal.py --manual      # start in explore mode instead of the dive
    python fractal.py --res 640x400 # sharper (slower deep down)
    python fractal.py --selftest    # headless checks, no window

Keys / mouse:
  Left click = zoom in on that point     Right click = zoom out     Mouse wheel = zoom at the cursor
  Arrows = pan     PageUp/PageDown = zoom      D = dive (screen-saver) mode      J = Julia set of the point under
  the mouse (press again to go back)     [ ] = palette speed     P = new palette     -/+ = fewer/more iterations
  Space = pause colours     R = reset view     F/Enter = fullscreen     S = screenshot     H = help     Esc/Q = quit
"""

import argparse
import math
import os
import random
import sys
import time

import numpy as np

from warp import PALETTES  # the seamless palettes from warp.py

HERE = os.path.dirname(os.path.abspath(__file__))
HOME_WIDTH = 3.4  # the classic view is this wide in the complex plane
HOME_CENTER = (-0.5, 0.0)
MIN_SCALE = 1e-13  # per-pixel size floor: below this a float64 runs out of digits and the picture goes blocky
DIVE_END = 2e-11

# Points found by *computation*, not memory: each was refined by zooming repeatedly toward the most detailed pixel,
# and the self-test checks they stay rich in detail at zoom 1e-9.
TARGETS = [
    ("Seahorse valley", -0.7435443420371511, 0.13677857090533),
    ("Triple spiral valley", -0.06311245890000003, 0.6681459213),
    ("Spiral", -0.7445564344, 0.12278524039999998),
    ("Deep spiral", -0.15267751099999996, 1.0351438386999998),
    ("Elephant valley", 0.27938628539999993, -0.009651499799999992),
    ("Misiurewicz spirals", -0.7479788230999999, -0.08973101239999999),
]


def compute(cx, cy, scale, w, h, max_iter, julia=None):
    """Escape-time picture of a w x h view centred on (cx, cy), `scale` complex units per pixel.

    Returns (nu, inside): a smooth iteration count per pixel and a mask of points that never escaped.
    julia=None -> Mandelbrot set; julia=c -> the Julia set for c. Pixels that escape are dropped from the
    working arrays as we go, so the cost follows the detailed pixels, not the whole picture."""
    xs = cx + (np.arange(w) + 0.5 - w / 2) * scale
    ys = cy + (np.arange(h) + 0.5 - h / 2) * scale
    plane = (xs[None, :] + 1j * ys[:, None]).ravel()
    n = plane.size
    nu = np.zeros(n, np.float32)
    inside = np.zeros(n, bool)
    if julia is None:
        px, py = plane.real, plane.imag
        q = (px - 0.25) ** 2 + py ** 2  # skip the main cardioid and the period-2 bulb: known to be inside
        skip = (q * (q + (px - 0.25)) < 0.25 * py ** 2) | ((px + 1) ** 2 + py ** 2 < 0.0625)
        z0, c_all = np.zeros(n, complex), plane
    else:
        skip = np.zeros(n, bool)
        z0, c_all = plane, np.full(n, julia, complex)
    inside[skip] = True
    act = np.flatnonzero(~skip)
    z, cc = z0[act], c_all[act]
    for i in range(max_iter):
        z = z * z + cc
        r2 = z.real * z.real + z.imag * z.imag
        esc = r2 > 65536.0  # a big bailout radius makes the colour bands smooth
        if esc.any():
            nu[act[esc]] = i + 1 - np.log2(0.5 * np.log(r2[esc]))
            keep = ~esc
            act, z, cc = act[keep], z[keep], cc[keep]
            if act.size == 0:
                break
    inside[act] = True
    return nu.reshape(h, w), inside.reshape(h, w)


def max_iter_for(scale, home_scale, mult=1.0):
    depth = max(0.0, math.log2(home_scale / scale))
    return int(min(4000, (96 + 42 * depth) * mult))


def to_index(nu, k=5.0):
    return (np.maximum(nu, 0) * k % 256).astype(np.uint8)


# -- Self-test ------------------------------------------------------------------------------------------------
def selftest() -> int:
    bad = 0

    def check(ok, what):
        nonlocal bad
        print(("PASS " if ok else "FAIL ") + what)
        bad += (not ok)

    def one(x, y, julia=None):  # a 1x1 view: the single pixel is exactly (x, y)
        return bool(compute(x, y, 1e-3, 1, 1, 300, julia)[1][0, 0])

    check(one(0, 0) and one(-1, 0) and one(0, 1) and one(-0.1, 0.1),
          "Mandelbrot: 0, -1, i and -0.1+0.1i are in the set")
    check(not one(1, 0) and not one(0.5, 0) and not one(-2.1, 0) and not one(0.3, 0.6),
          "Mandelbrot: 1, 0.5, -2.1 and 0.3+0.6i escape")
    check(one(0.5, 0, 0j) and one(0, 0.9, 0j) and not one(1.5, 0, 0j) and not one(0, 1.1, 0j),
          "Julia c=0: the set is the unit disk")

    nu, ins = compute(-0.5, 0, 0.01, 64, 50, 200)
    check(bool((ins == ins[::-1]).all()) and np.allclose(nu, nu[::-1], atol=1e-3),
          "the picture is mirror-symmetric about the real axis, as the maths says")

    t0 = time.perf_counter()
    compute(*HOME_CENTER, HOME_WIDTH / 320, 320, 200, 100)
    ms = (time.perf_counter() - t0) * 1000
    print(f"     (info) the classic 320x200 view took {ms:.0f} ms")

    home_scale = HOME_WIDTH / 320
    for name, x, y in TARGETS:
        nu, ins = compute(x, y, 1e-9, 320, 200, max_iter_for(1e-9, home_scale))
        distinct = len(np.unique(to_index(nu)[~ins])) if (~ins).any() else 0
        check(distinct >= 100 and ins.mean() < 0.9, f"target '{name}' still full of detail at zoom 1e-9 ({distinct} colours)")

    its = [max_iter_for(s, home_scale) for s in (1e-2, 1e-4, 1e-8, 1e-12, 1e-20)]
    check(its == sorted(its) and its[-1] <= 4000, f"iteration budget grows with depth and is capped: {its}")
    print("ALL PASSED" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


# -- The window -----------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Mandelbrot / Julia zoomer with palette cycling")
    ap.add_argument("--res", default="320x200", help="drawing size; the DOS 320x200 by default")
    ap.add_argument("--rate", type=float, default=0.9, help="dive speed, in zoom doublings per second")
    ap.add_argument("--speed", type=float, default=30.0, help="palette colours per second")
    ap.add_argument("--manual", action="store_true", help="start in explore mode")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    import pygame

    w, h = (int(n) for n in args.res.lower().split("x"))
    rng = random.Random(args.seed if args.seed is not None else time.time_ns())
    home_scale = HOME_WIDTH / w

    pygame.init()
    screen = pygame.display.set_mode((w, h), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Bordeom - fractal")
    canvas = pygame.Surface((w, h))
    font = pygame.font.Font(None, 16)
    clock = pygame.time.Clock()

    view = {"cx": HOME_CENTER[0], "cy": HOME_CENTER[1], "scale": home_scale}
    st = {"julia": None, "saved": None, "idx": np.zeros((h, w), np.uint8), "inside": np.zeros((h, w), bool),
          "ms": 0.0, "step": 1, "mult": 1.0, "dirty": True, "pal": None, "pal_name": ""}
    dive = {"on": not args.manual, "target": None, "phase": "in", "t": 0.0, "order": []}
    fade = 0.9

    def new_palette():
        st["pal_name"], pf = rng.choice(PALETTES)
        st["pal"] = pf(rng)

    def pick_target():
        if not dive["order"]:
            dive["order"] = list(range(len(TARGETS)))
            rng.shuffle(dive["order"])
        dive["target"] = TARGETS[dive["order"].pop()]
        view.update(cx=HOME_CENTER[0], cy=HOME_CENTER[1], scale=home_scale)

    def start_dive():
        dive.update(on=True, phase="in", t=0.0)
        st["julia"] = None
        pick_target()
        st["dirty"] = True

    def recompute():
        step = st["step"]
        cw, ch = -(-w // step), -(-h // step)
        it = max_iter_for(view["scale"], home_scale, st["mult"])
        t0 = time.perf_counter()
        nu, ins = compute(view["cx"], view["cy"], view["scale"] * step, cw, ch, it, st["julia"])
        st["ms"] = (time.perf_counter() - t0) * 1000
        idx = to_index(nu)
        if step > 1:
            idx = np.repeat(np.repeat(idx, step, 0), step, 1)[:h, :w]
            ins = np.repeat(np.repeat(ins, step, 0), step, 1)[:h, :w]
        st["idx"], st["inside"], st["dirty"] = idx, ins, False
        cost = st["ms"] * (step * step)  # what a full-size frame would have cost
        if step == 1 and st["ms"] > 300 and dive["on"]:
            st["step"] = 2  # deep down, draw at half size while diving so it keeps moving
        elif step == 2 and cost < 200:
            st["step"] = 1

    def point(px, py):
        return (view["cx"] + (px + 0.5 - w / 2) * view["scale"], view["cy"] + (py + 0.5 - h / 2) * view["scale"])

    def zoom_at(px, py, factor):
        x, y = point(px, py)
        new = min(home_scale * 1.2, max(MIN_SCALE, view["scale"] * factor))
        f = new / view["scale"]
        view.update(cx=x + (view["cx"] - x) * f, cy=y + (view["cy"] - y) * f, scale=new)
        dive["on"] = False
        st["dirty"] = True

    def reset_view():
        st["julia"] = None
        view.update(cx=HOME_CENTER[0], cy=HOME_CENTER[1], scale=home_scale)
        dive["on"] = False
        st["dirty"] = True

    new_palette()
    if dive["on"]:
        pick_target()
    offset, speed, paused, help_on, running = 0.0, args.speed, False, True, True
    bright, note, note_until = 0.0, "", 0.0

    while running:
        dt = min(clock.tick(60) / 1000.0, 0.25)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                x, y = point(*ev.pos)
                view.update(cx=x, cy=y)  # re-centre on the click, then zoom about it
                zoom_at(w / 2, h / 2, 0.5 if ev.button == 1 else 2.0)
            elif ev.type == pygame.MOUSEWHEEL and ev.y:
                zoom_at(*pygame.mouse.get_pos(), 0.8 ** ev.y)
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                pan = view["scale"] * w * 0.1
                if k in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif k == pygame.K_LEFT:
                    view["cx"] -= pan; dive["on"] = False; st["dirty"] = True
                elif k == pygame.K_RIGHT:
                    view["cx"] += pan; dive["on"] = False; st["dirty"] = True
                elif k == pygame.K_UP:
                    view["cy"] -= pan; dive["on"] = False; st["dirty"] = True
                elif k == pygame.K_DOWN:
                    view["cy"] += pan; dive["on"] = False; st["dirty"] = True
                elif k == pygame.K_PAGEUP:
                    zoom_at(w / 2, h / 2, 0.7)
                elif k == pygame.K_PAGEDOWN:
                    zoom_at(w / 2, h / 2, 1 / 0.7)
                elif k == pygame.K_d:
                    start_dive()
                elif k == pygame.K_j:
                    if st["julia"] is None:
                        c = point(*pygame.mouse.get_pos())
                        st["saved"], st["julia"] = dict(view), complex(*c)
                        view.update(cx=0.0, cy=0.0, scale=3.0 / w)
                        note = f"Julia set for c = {c[0]:.5f} {c[1]:+.5f}i"
                    else:
                        view.update(st["saved"])
                        st["julia"], note = None, "back to the Mandelbrot set"
                    note_until, dive["on"], st["dirty"] = time.time() + 3.0, False, True
                elif k == pygame.K_p:
                    new_palette()
                elif k == pygame.K_LEFTBRACKET:
                    speed = math.copysign(max(2.0, abs(speed) / 1.25), speed)
                elif k == pygame.K_RIGHTBRACKET:
                    speed = math.copysign(min(300.0, abs(speed) * 1.25), speed)
                elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    st["mult"] = max(0.25, st["mult"] / 1.25); st["dirty"] = True
                elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    st["mult"] = min(4.0, st["mult"] * 1.25); st["dirty"] = True
                elif k == pygame.K_SPACE:
                    paused = not paused
                elif k == pygame.K_r:
                    reset_view()
                elif k in (pygame.K_f, pygame.K_RETURN):
                    try:
                        pygame.display.toggle_fullscreen()
                    except pygame.error:  # e.g. a display driver that can't go fullscreen
                        pass
                elif k == pygame.K_h:
                    help_on = not help_on
                elif k == pygame.K_s:
                    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
                    path = os.path.join(HERE, "shots", time.strftime("fractal-%Y%m%d-%H%M%S.png"))
                    pygame.image.save(pygame.transform.scale(canvas, (w * 3, h * 3)), path)
                    note, note_until = "saved " + os.path.basename(path), time.time() + 2.0

        if dive["on"]:  # fall toward the target at a steady rate of doublings per second
            dive["t"] += dt
            if dive["phase"] == "in":
                bright = min(1.0, dive["t"] / fade)
                if dive["t"] >= fade:
                    dive.update(phase="go", t=0.0)
            elif dive["phase"] == "go":
                bright = 1.0
                new = view["scale"] * 2.0 ** (-args.rate * dt)
                f = new / view["scale"]
                _, tx, ty = dive["target"]
                view.update(cx=tx + (view["cx"] - tx) * f, cy=ty + (view["cy"] - ty) * f, scale=new)
                st["dirty"] = True
                if new <= DIVE_END:
                    dive.update(phase="hold", t=0.0)
            elif dive["phase"] == "hold":
                if dive["t"] >= 4.0:
                    dive.update(phase="out", t=0.0)
            else:
                bright = max(0.0, 1.0 - dive["t"] / fade)
                if dive["t"] >= fade:
                    pick_target()
                    new_palette()
                    dive.update(phase="in", t=0.0)
                    bright = 0.0
            if dive["phase"] in ("go", "hold"):
                note = f"{dive['target'][0]}"
                note_until = time.time() + 0.5
        else:
            bright = 1.0

        if st["dirty"]:
            recompute()
        if not paused:
            offset = (offset + speed * dt) % 256.0

        rgb = np.roll(st["pal"], int(offset), axis=0)
        img = rgb[st["idx"]]
        img[st["inside"]] = 0
        if bright < 1.0:
            img = (img * bright).astype(np.uint8)
        pygame.surfarray.blit_array(canvas, np.ascontiguousarray(img.swapaxes(0, 1)))

        mag = home_scale / view["scale"]
        mode = "Julia" if st["julia"] is not None else "Mandelbrot"
        lines = [f"{mode}  zoom {mag:.3g}x  iter {max_iter_for(view['scale'], home_scale, st['mult'])}  "
                 f"{st['ms']:.0f} ms" + ("  [dive]" if dive["on"] else "")]
        if time.time() < note_until:
            lines.append(note)
        if help_on:
            lines += ["click zoom in / right-click out / wheel  arrows pan  D dive  J julia",
                      "P palette  [ ] speed  -/+ iterations  R reset  S shot  H help  Q quit"]
        for n, text in enumerate(lines):
            for dx, dy, col in ((1, 1, (0, 0, 0)), (0, 0, (255, 255, 255))):
                canvas.blit(font.render(text, False, col), (3 + dx, 3 + n * 10 + dy))
        screen.blit(canvas, (0, 0))
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
