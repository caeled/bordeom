"""A local surprise. Run this file; no extra packages required."""
import argparse
import colorsys
import math
from pathlib import Path
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET


def make_curve(seed, count=4200):
    rng = random.Random(seed)
    outer = rng.randint(5, 13)
    inner = rng.choice([n for n in range(2, outer) if math.gcd(n, outer) == 1])
    offset = rng.uniform(0.7, 1.7) * inner
    scale = outer - inner + offset
    points = []
    for i in range(count + 1):
        t = i / count * math.tau * inner
        x = ((outer-inner)*math.cos(t) + offset*math.cos((outer-inner)/inner*t))/scale
        y = ((outer-inner)*math.sin(t) - offset*math.sin((outer-inner)/inner*t))/scale
        points.append((x, y))
    return points


def color(index, seed):
    rgb = colorsys.hsv_to_rgb((index / 4200 + random.Random(seed).random()) % 1, .7, 1)
    return '#' + ''.join(f'{round(c*255):02x}' for c in rgb)


def svg_text(seed):
    points = make_curve(seed)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="-1.12 -1.12 2.24 2.24">',
             '<rect x="-1.12" y="-1.12" width="2.24" height="2.24" fill="#080d19"/>']
    for i in range(0, len(points)-1, 20):
        coords = ' '.join(f'{x:.6f},{y:.6f}' for x,y in points[i:i+21])
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color(i, seed)}" stroke-width="0.003"/>')
    parts.append('</svg>')
    return '\n'.join(parts)


class App:
    def __init__(self, root, seed):
        import tkinter as tk
        from tkinter import filedialog, messagebox
        self.root, self.tk = root, tk
        self.filedialog, self.messagebox = filedialog, messagebox
        self.seed = seed
        self.paused = False
        self.index = 0
        root.title('Bordeom — Pocket Orbit')
        root.geometry('900x760')
        root.minsize(500, 400)
        root.configure(bg='#080d19')
        toolbar = tk.Frame(root, bg='#080d19')
        toolbar.pack(fill='x', padx=14, pady=10)
        for label, command in [('Another orbit', self.new), ('Pause / resume', self.pause), ('Save artwork…', self.save)]:
            tk.Button(toolbar, text=label, command=command).pack(side='left', padx=4)
        self.status = tk.Label(root, bg='#080d19', fg='#ccd6ef', anchor='w')
        self.status.pack(side='bottom', fill='x', padx=18, pady=10)
        self.canvas = tk.Canvas(root, bg='#080d19', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', self.resize)
        root.bind('<space>', lambda e: self.pause())
        root.bind('n', lambda e: self.new())
        root.bind('s', lambda e: self.save())
        root.bind('<Escape>', lambda e: root.destroy())
        self.reset()
        self.timer = root.after(16, self.tick)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def reset(self):
        self.points = make_curve(self.seed)
        self.index = 0
        self.canvas.delete('all')
        self.status.config(text=f'Seed {self.seed}  ·  Space: pause  ·  N: another  ·  S: save  ·  Esc: close')

    def new(self):
        self.seed = random.SystemRandom().randrange(2**32)
        self.paused = False
        self.reset()

    def pause(self):
        self.paused = not self.paused

    def draw(self, start, end):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = min(w,h) * .44
        coords = []
        for x,y in self.points[start:end+1]:
            coords.extend((w/2+x*scale, h/2+y*scale))
        if len(coords) >= 4:
            self.canvas.create_line(*coords, fill=color(start, self.seed), width=1.4)

    def resize(self, event=None):
        self.canvas.delete('all')
        for i in range(0, self.index, 20):
            self.draw(i, min(i+20, self.index))

    def tick(self):
        if not self.paused and self.index < len(self.points)-1:
            end = min(self.index+20, len(self.points)-1)
            self.draw(self.index, end)
            self.index = end
        self.timer = self.root.after(16, self.tick)

    def save(self):
        name = self.filedialog.asksaveasfilename(defaultextension='.svg',
            initialfile=f'orbit-{self.seed}.svg', filetypes=[('SVG artwork', '*.svg')])
        if name:
            try:
                Path(name).write_text(svg_text(self.seed), encoding='utf-8')
                self.status.config(text=f'Saved {Path(name).name}')
            except OSError as exc:
                self.messagebox.showerror('Could not save', str(exc))

    def close(self):
        self.root.after_cancel(self.timer)
        self.root.destroy()


class Checks(unittest.TestCase):
    def test_closed_and_bounded(self):
        for seed in range(30):
            points = make_curve(seed)
            self.assertEqual(len(points), 4201)
            self.assertTrue(all(math.isfinite(x) and math.isfinite(y) and math.hypot(x,y) <= 1.000001 for x,y in points))
            self.assertLess(math.dist(points[0], points[-1]), 1e-10)

    def test_repeatability_and_variation(self):
        self.assertEqual(make_curve(42), make_curve(42))
        self.assertNotEqual(make_curve(42), make_curve(43))

    def test_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'art.svg'
            path.write_text(svg_text(42), encoding='utf-8')
            tree = ET.parse(path)
            lines = tree.findall('.//{http://www.w3.org/2000/svg}polyline')
            self.assertEqual(len(lines), 210)
            self.assertEqual(lines[0].attrib['points'].split()[0], lines[-1].attrib['points'].split()[-1])


def main():
    parser = argparse.ArgumentParser(description='Open the surprise locally.')
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--export', type=Path, help='Save an SVG without opening a window')
    args = parser.parse_args()
    if args.selftest:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
        return 0 if result.wasSuccessful() else 1
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**32)
    if args.export:
        args.export.write_text(svg_text(seed), encoding='utf-8')
        return 0
    import tkinter as tk
    root = tk.Tk()
    App(root, seed)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
