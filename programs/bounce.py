"""Bordeom / bounce.py -- a bouncing line, in the spirit of the old DOS screen savers (Mystify and friends).

Two endpoints fly around and reflect off all four walls; the line between them, with a fading trail, is the show.
After a random period the NEXT BOUNCE is special:
    - if there is only one line, it splits into 2-4 lines that fan out;
    - if there are already several, the line that just bounced dies (so there is always at least one).

    python bounce.py                # play (Esc or Q quits)
    python bounce.py --seed 42      # repeatable run
    python bounce.py --period 2 5   # event every 2-5 seconds (random each time)
    python bounce.py --rhythm nested  # the old BASIC INT(RND) trick: mostly short waits, rare long ones (T switches live)
    python bounce.py --selftest     # headless physics + event checks, no window

Randomness: NumPy's PCG64 generator, seeded from the operating system's entropy unless --seed is given.

Keys: Space = pause   Up/Down = speed   R = restart   F or Enter = fullscreen   S = screenshot   H = help   Esc/Q = quit
"""

import argparse
import colorsys
import math
import os
import sys
import time
from collections import Counter, deque
from datetime import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# -- Reflection: exact for any step size (even a step that crosses the screen twice) -------------------------
def reflect(x, v, length):
    """Fold positions x (array) back into [0, length] as if bouncing between two walls.

    Returns (x, v, n) where v has its sign flipped once per odd number of bounces and n is the bounce count.
    Unfolding the path (a bounce is a mirror) makes this exact: fold = position on a repeating zig-zag."""
    k = np.floor(x / length)
    r = x - k * length
    odd = (k.astype(np.int64) % 2) != 0
    return np.where(odd, length - r, r), np.where(odd, -v, v), np.abs(k).astype(np.int64)


def random_direction(rng):
    """A random unit vector that is never close to an axis, so all four walls get used."""
    while True:
        a = rng.uniform(0.0, 2 * math.pi)
        c, s = math.cos(a), math.sin(a)
        if min(abs(c), abs(s)) >= 0.25:
            return np.array([c, s])


# -- The simulation (no pygame in here, so it can be tested without a window) ------------------------------
class Line:
    def __init__(self, p, v, hue, trail_len):
        self.p = np.array(p, dtype=np.float64)  # [[x1, y1], [x2, y2]]
        self.v = np.array(v, dtype=np.float64)  # pixels per second
        self.hue = hue
        self.trail = deque(maxlen=trail_len)  # (endpoints, hue) snapshots, oldest first
        self.dying = False


RHYTHMS = ("flat", "nested", "deep")
CYCLE = ("day",) + RHYTHMS   # what the T key steps through; "day" is what you get when you name no rhythm (shown as "default")

# The quiet default: each weekday keys its own letter in Morse, M T W R F S U (the letters used for Monday..Sunday in course
# timetables, so Tuesday and Thursday, Saturday and Sunday differ). A dot is one time unit between special bounces, a dash three,
# and the letter's last wait is stretched by six units (the pause between letters); then the letter repeats. It reads the
# computer's clock (no time server), so a wrong clock keys the wrong day. Nothing on screen or in --help says so.
DAY_LETTERS = "MTWRFSU"                                        # index = datetime.weekday(): Monday is 0
MORSE = {"M": "--", "T": "-", "W": ".--", "R": ".-.", "F": "..-.", "S": "...", "U": "..-"}


def day_pattern(weekday):
    """The waits, in time units, that key this weekday's letter: dot 1, dash 3, the last one plus 6 (letter space)."""
    waits = [1 if c == "." else 3 for c in MORSE[DAY_LETTERS[weekday]]]
    waits[-1] += 6
    return waits


def decode_pattern(waits):
    """Inverse of day_pattern, used by the self-test: the Morse elements of a list of waits."""
    return "".join("." if w in (1, 7) else "-" for w in waits)


class Sim:
    def __init__(self, w, h, rng, speed=220.0, period=(3.0, 9.0), trail_len=36, rhythm="day", day=None):
        self.w, self.h, self.rng, self.speed, self.period, self.trail_len = w, h, rng, speed, period, trail_len
        self.rhythm = rhythm
        self.pattern = day_pattern(datetime.now().weekday() if day is None else day)   # for the "day" rhythm
        self.pidx = 0
        self.lines, self.ghosts = [], []
        self.walls = Counter()  # how often each wall was hit: L R T B
        self.lines.append(self.new_line())
        self.timer = self.next_period()
        self.armed = False

    def next_period(self):
        """Seconds until the next bounce is special.

        flat:   evenly random between the two limits.
        nested: the old BASIC trick INT(RND(1)*(INT(RND(1)*N)+1))+1 -- one draw sets the ceiling for the next.
                In continuous form that is a product of random numbers: mostly short waits, an occasional long one.
        deep:   three draws deep, so even more bursts and even rarer long pauses.
        day:    not random: the weekday's Morse letter, one wait per element (see day_pattern); unit = (lo + hi) / 12 s."""
        lo, hi = self.period
        if self.rhythm == "day":
            unit = (lo + hi) / 12.0
            wait = self.pattern[self.pidx % len(self.pattern)] * unit
            self.pidx += 1
            return wait
        if self.rhythm == "flat":
            return float(self.rng.uniform(lo, hi))
        u = 1.0
        for _ in range(2 if self.rhythm == "nested" else 3):
            u *= float(self.rng.random())
        return lo + (hi - lo) * u

    def new_line(self):
        p = [[self.rng.uniform(0, self.w - 1), self.rng.uniform(0, self.h - 1)] for _ in range(2)]
        v = [random_direction(self.rng) * self.speed * self.rng.uniform(0.75, 1.25) for _ in range(2)]
        return Line(p, v, float(self.rng.random()), self.trail_len)

    def step(self, dt):
        """Advance dt seconds. Returns a list of events: ('split'|'kill', lines_before, lines_after)."""
        events = []
        if not self.armed:
            self.timer -= dt
            self.armed = self.timer <= 0
        for line in list(self.lines):
            hit = self._advance(line, dt)
            line.hue = (line.hue + dt * 0.04) % 1.0
            line.trail.append((line.p.copy(), line.hue))
            if hit and self.armed:
                self.armed, self.timer = False, self.next_period()
                before = len(self.lines)
                if before == 1:
                    self._split(line)
                    events.append(("split", before, len(self.lines)))
                else:
                    line.dying = True
                    self.lines.remove(line)
                    self.ghosts.append(line)
                    events.append(("kill", before, len(self.lines)))
        for g in list(self.ghosts):  # a dead line's trail drains away
            if g.trail:
                g.trail.popleft()
            if not g.trail:
                self.ghosts.remove(g)
        return events

    def _advance(self, line, dt):
        line.p += line.v * dt
        hit = False
        for axis, length, low, high in ((0, self.w - 1, "L", "R"), (1, self.h - 1, "T", "B")):
            before = np.floor(line.p[:, axis] / length)
            x, v, n = reflect(line.p[:, axis], line.v[:, axis], length)
            line.p[:, axis], line.v[:, axis] = x, v
            for k, count in zip(before, n):
                if count:
                    hit = True
                    first = low if k < 0 else high
                    self.walls[first] += 1
                    if count > 1:  # crossed to the far wall as well
                        self.walls[high if first == low else low] += 1
        return hit

    def _split(self, parent):
        for _ in range(int(self.rng.integers(1, 4))):  # 1-3 children: 2-4 lines in all
            a = math.radians(self.rng.uniform(12, 70)) * (1 if self.rng.random() < 0.5 else -1)
            c, s = math.cos(a), math.sin(a)
            rot = np.array([[c, -s], [s, c]])  # a rotation keeps speed the same
            child = Line(parent.p, parent.v @ rot.T, (parent.hue + self.rng.uniform(0.05, 0.3)) % 1.0, self.trail_len)
            self.lines.append(child)


# -- Self-test -----------------------------------------------------------------------------------------------
def selftest() -> int:
    import numpy.random as npr

    bad = 0

    def check(ok, what):
        nonlocal bad
        print(("PASS " if ok else "FAIL ") + what)
        bad += (not ok)

    # 1. reflection maths, including steps that cross the screen more than once
    x, v, n = reflect(np.array([-3.0, 104.0, 250.0, -250.0, 60.0]), np.array([-2.0, 5.0, 5.0, -5.0, 1.0]), 100.0)
    check(np.allclose(x, [3, 96, 50, 50, 60]) and (v == [2, -5, 5, 5, 1]).all() and list(n) == [1, 1, 2, 3, 0],
          "reflect: single, double and triple crossings fold back correctly")

    # 2. one line, no events, many steps (some huge): stays on screen, keeps its speed, uses all four walls
    sim = Sim(640, 400, npr.default_rng(5), period=(1e9, 1e9))
    speeds0 = np.linalg.norm(sim.lines[0].v, axis=1)
    inside = True
    for i in range(60000):
        sim.step(0.5 if i % 997 == 0 else 1 / 60)
        p = sim.lines[0].p
        inside &= bool((p[:, 0] >= 0).all() and (p[:, 0] <= 639).all() and (p[:, 1] >= 0).all() and (p[:, 1] <= 399).all())
    check(inside, "60000 steps: both endpoints always inside the screen")
    check(np.allclose(np.linalg.norm(sim.lines[0].v, axis=1), speeds0), "bouncing never changes an endpoint's speed")
    check(all(sim.walls[s] > 100 for s in "LRTB"), f"all four walls used: {dict(sim.walls)}")

    # 3. the split / kill rule over a long random run
    sim = Sim(640, 400, npr.default_rng(11), period=(0.2, 0.8))
    splits = kills = 0
    ok_rule, ok_range = True, True
    for _ in range(120000):
        for kind, before, after in sim.step(1 / 60):
            if kind == "split":
                splits += 1
                ok_rule &= (before == 1 and 2 <= after <= 4)
            else:
                kills += 1
                ok_rule &= (before > 1 and after == before - 1)
        ok_range &= 1 <= len(sim.lines) <= 4
    check(ok_rule, f"split only from 1 line (to 2-4); a kill only when several ({splits} splits, {kills} kills)")
    check(ok_range and splits > 20 and kills > 20, "line count stays between 1 and 4 and both events keep happening")

    # 4. dead lines' trails drain and disappear
    check(len(sim.ghosts) <= 3, "dead lines' trails drain away")

    # 5. repeatable with a seed, different without one
    def run(seed):
        s = Sim(640, 400, npr.default_rng(seed), period=(0.2, 0.8))
        for _ in range(5000):
            s.step(1 / 60)
        return len(s.lines), [round(float(t), 6) for line in s.lines for t in line.p.ravel()]

    check(run(3) == run(3) and run(3) != run(4), "same seed repeats exactly; another seed differs")

    # 6. the three rhythms: all inside the limits, with the averages the maths predicts (mean of u, u*u, u*u*u)
    means = {}
    for name in RHYTHMS:
        s = Sim(640, 400, npr.default_rng(9), period=(3.0, 9.0), rhythm=name)
        d = np.array([s.next_period() for _ in range(40000)])
        means[name] = float(d.mean())
        check(d.min() >= 3.0 and d.max() <= 9.0, f"rhythm {name}: every wait between 3 and 9 s (mean {d.mean():.2f} s)")
    check(abs(means["flat"] - 6.0) < 0.1 and abs(means["nested"] - 4.5) < 0.1 and abs(means["deep"] - 3.75) < 0.1,
          "means match the maths: flat 6.00, nested 4.50, deep 3.75")

    # 7. the day rhythm: seven distinct letters, keyed exactly, and events never come sooner than the key says
    check(len({DAY_LETTERS[d] for d in range(7)}) == 7 and DAY_LETTERS == "MTWRFSU" and datetime(2026, 9, 21).weekday() == 0,
          "seven weekdays, seven different letters M T W R F S U (Monday = 0)")
    pats = [day_pattern(d) for d in range(7)]
    check(pats == [[3, 9], [9], [1, 3, 9], [1, 3, 7], [1, 1, 3, 7], [1, 1, 7], [1, 1, 9]] and len({tuple(q) for q in pats}) == 7,
          "the seven patterns are exactly as designed and all differ")
    check(all(decode_pattern(pats[d]) == MORSE[DAY_LETTERS[d]] for d in range(7)), "each pattern decodes back to its letter")
    ok_seq = True
    for d in range(7):
        s = Sim(640, 400, npr.default_rng(1), period=(3.0, 9.0), rhythm="day", day=d)   # unit = 1 s
        got = [s.timer] + [s.next_period() for _ in range(2 * len(pats[d]) - 1)]      # the first wait was drawn on creation
        ok_seq &= got == [float(x) for x in pats[d]] * 2
    s = Sim(640, 400, npr.default_rng(1), period=(2.0, 4.0), rhythm="day", day=2)       # unit = 0.5 s
    ok_seq &= [s.timer, s.next_period(), s.next_period()] == [0.5, 1.5, 4.5]
    check(ok_seq, "the day rhythm repeats its letter exactly, and its unit follows --period")
    ok_gap, events_seen = True, 0
    for d in (0, 3, 5):                       # M, R, S with a fast unit (0.05 s): an event may come late (it waits for a wall) but never early
        s = Sim(640, 400, npr.default_rng(2), period=(0.3, 0.3), rhythm="day", day=d)
        t, last, k = 0.0, 0.0, 0
        for _ in range(60000):
            t += 1 / 60
            for _ev in s.step(1 / 60):
                want = pats[d][k % len(pats[d])] * 0.05
                ok_gap &= (t - last) >= want - 1 / 60 - 1e-9
                last, k, events_seen = t, k + 1, events_seen + 1
    check(ok_gap and events_seen > 300, f"events follow the key and are never early ({events_seen} events over three days)")
    print("ALL PASSED" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


# -- The window ----------------------------------------------------------------------------------------------
def draw(canvas, sim, pygame):
    canvas.fill((0, 0, 0))
    for line in sim.lines + sim.ghosts:
        m = len(line.trail)
        for i, (pts, hue) in enumerate(line.trail):
            b = ((i + 1) / m) ** 1.6
            r, g, bl = colorsys.hsv_to_rgb(hue, 0.85, b)
            pygame.draw.line(canvas, (int(r * 255), int(g * 255), int(bl * 255)), pts[0], pts[1], 1)
        if not line.dying and m:
            for pt in line.trail[-1][0]:
                pygame.draw.circle(canvas, (255, 255, 255), (int(pt[0]), int(pt[1])), 2)


def shown(rhythm):
    return "default" if rhythm == "day" else rhythm


def main() -> int:
    ap = argparse.ArgumentParser(description="A bouncing line that splits and dies at random")
    ap.add_argument("--res", default="640x400")
    ap.add_argument("--speed", type=float, default=220.0, help="pixels per second")
    ap.add_argument("--period", type=float, nargs=2, default=(3.0, 9.0), metavar=("MIN", "MAX"),
                    help="seconds until the next bounce triggers a split or a kill (random in this range)")
    ap.add_argument("--rhythm", choices=RHYTHMS, default=None,
                    help="flat = even random waits; nested = the old BASIC INT(RND) trick (mostly short waits, "
                         "rare long ones); deep = three deep. T switches it while running. Default: the built-in one")
    ap.add_argument("--day", type=int, choices=range(7), default=None, help=argparse.SUPPRESS)   # test aid: pretend it is weekday 0-6
    ap.add_argument("--trail", type=int, default=36, help="length of the fading trail, in frames")
    ap.add_argument("--seed", type=int, default=None, help="repeatable run (default: seeded from OS entropy)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    import pygame

    w, h = (int(n) for n in args.res.lower().split("x"))

    rhythm = [args.rhythm or "day"]  # a list so the T key can change it and R (restart) keeps it

    def fresh():
        return Sim(w, h, np.random.default_rng(args.seed), args.speed, tuple(args.period), args.trail, rhythm[0], args.day)

    sim = fresh()
    pygame.init()
    screen = pygame.display.set_mode((w, h), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Bordeom - bounce")
    canvas = pygame.Surface((w, h))
    font = pygame.font.Font(None, 20)
    clock = pygame.time.Clock()
    paused, help_on, speed_mult, note, note_until = False, True, 1.0, "", 0.0
    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif k == pygame.K_SPACE:
                    paused = not paused
                elif k == pygame.K_UP:
                    speed_mult = min(4.0, speed_mult * 1.25)
                elif k == pygame.K_DOWN:
                    speed_mult = max(0.2, speed_mult / 1.25)
                elif k == pygame.K_r:
                    sim = fresh()
                elif k == pygame.K_t:
                    rhythm[0] = CYCLE[(CYCLE.index(rhythm[0]) + 1) % len(CYCLE)]
                    sim.rhythm = rhythm[0]  # takes effect from the next wait
                    note, note_until = f"rhythm: {shown(rhythm[0])}", time.time() + 2.0
                elif k in (pygame.K_f, pygame.K_RETURN):
                    try:
                        pygame.display.toggle_fullscreen()
                    except pygame.error:  # e.g. a display driver that can't go fullscreen
                        pass
                elif k == pygame.K_h:
                    help_on = not help_on
                elif k == pygame.K_s:
                    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
                    path = os.path.join(HERE, "shots", time.strftime("bounce-%Y%m%d-%H%M%S.png"))
                    pygame.image.save(canvas, path)
                    note, note_until = "saved " + os.path.basename(path), time.time() + 2.0
        if not paused:
            for kind, before, after in sim.step(dt * speed_mult):
                note, note_until = f"{kind.upper()}: {before} -> {after} lines", time.time() + 2.0
        draw(canvas, sim, pygame)
        lines = [f"lines: {len(sim.lines)}   rhythm: {shown(sim.rhythm)}"]
        if time.time() < note_until:
            lines.append(note)
        if help_on:
            lines += ["Space pause  Up/Down speed  R restart  T rhythm  F fullscreen  S shot  H help  Q quit"]
        for n, text in enumerate(lines):
            canvas.blit(font.render(text, False, (200, 200, 200)), (6, 4 + n * 16))
        screen.blit(canvas, (0, 0))
        pygame.display.flip()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
