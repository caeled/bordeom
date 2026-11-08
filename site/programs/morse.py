"""Bordeom / morse.py -- type something, hear it in Morse code. For Dad (a ham since 1956).

    python morse.py                          # a little window: type, press Go
    python morse.py "CQ CQ" --wpm 15         # or send from the command line
    python morse.py "73" --save 73.wav       # write the audio to a WAV file instead (the window has a Save WAV button)
    python morse.py "CQ CQ" --wpm 20 --fwpm 8 --loops 0    # letters at 20 WPM, overall 8 WPM, repeat until Ctrl+C
    python morse.py "CQ" --save cq.wav --seconds 300       # a WAV that repeats the message to fill at least 5 minutes
    python morse.py --selftest               # timing and code-table checks, no sound

Timing is the standard one: a dit is 1200/WPM milliseconds; a dah is 3 dits; the gap inside a letter is 1 dit,
between letters 3 dits, between words 7 dits. (So the word PARIS plus its word gap is exactly 50 dits, which is
how "words per minute" is defined.) Windows only: the beeps come from winsound.

Learning aids:
  * Farnsworth spacing (--fwpm): the letters are still sent at full speed (--wpm) so each one sounds like real Morse, but
    the gaps between letters and words are stretched until the OVERALL speed is fwpm. Standard formula: one spacing unit
    = (60/fwpm - 37.2/wpm) / 19 seconds, with 3 units between letters and 7 between words.
  * Loops (--loops N, 0 = until stopped): the message repeats with a pause of three word gaps between repeats.
  * Hide (in the window): don't show the dots and dashes while it plays, so you learn by ear; Reveal shows them.
"""

import argparse
import math
import sys
import threading
import time

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.", "G": "--.", "H": "....", "I": "..",
    "J": ".---", "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--", "/": "-..-.", "(": "-.--.",
    ")": "-.--.-", "&": ".-...", ":": "---...", ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-",
    '"': ".-..-.", "@": ".--.-.",
}
MAX_EXPORT_SECONDS = 1800  # a WAV is about 5 MB per minute, so cap an export at half an hour


def words_of(text):
    """The text as a list of words, each a list of Morse letters (characters with no code are skipped)."""
    words = [[MORSE[c] for c in w if c in MORSE] for w in text.upper().split()]
    return [w for w in words if w]


def encode(text):
    """Dots and dashes as text: letters separated by a space, words by ' / '."""
    return " / ".join(" ".join(w) for w in words_of(text))


def schedule(text):
    """The sound as a list of (tone_on, length_in_dits)."""
    out = []
    words = words_of(text)
    for wi, word in enumerate(words):
        for li, code in enumerate(word):
            for ei, e in enumerate(code):
                out.append((True, 1 if e == "." else 3))
                if ei < len(code) - 1:
                    out.append((False, 1))
            if li < len(word) - 1:
                out.append((False, 3))
        if wi < len(words) - 1:
            out.append((False, 7))
    return out


def spacing(wpm, fwpm=None):
    """Seconds in one 'spacing unit' (3 of them between letters, 7 between words). Equals one dit unless Farnsworth."""
    fwpm = min(fwpm or wpm, wpm)
    return 1.2 / wpm if fwpm >= wpm else (60.0 / fwpm - 37.2 / wpm) / 19.0


def timeline(text, wpm, fwpm=None):
    """The sound as a list of (tone_on, seconds). wpm = speed of the letters, fwpm = overall speed (Farnsworth)."""
    dit, space = 1.2 / wpm, spacing(wpm, fwpm)
    return [(on, u * (dit if (on or u == 1) else space)) for on, u in schedule(text)]


def loop_pause(wpm, fwpm=None):
    """The silence between repeats: three word gaps."""
    return 21 * spacing(wpm, fwpm)


def play(text, wpm, hz, stop=None, fwpm=None, loops=1):
    """Beep the message. loops=0 repeats until `stop` is set (or forever)."""
    import winsound

    tl, pause = timeline(text, wpm, fwpm), loop_pause(wpm, fwpm)
    if not tl:
        return
    def wait_until(t):  # sleep until time t, but wake every 20 ms so Stop cuts in at once. False if stopped.
        while True:
            left = t - time.perf_counter()
            if stop is not None and stop.is_set():
                return False
            if left <= 0:
                return True
            time.sleep(min(left, 0.02))

    t0, at, done = time.perf_counter(), 0.0, 0  # every element starts at its exact time: call overhead never adds up
    while loops == 0 or done < loops:
        for on, secs in tl:
            if not wait_until(t0 + at):
                return
            if on:
                winsound.Beep(int(hz), max(1, int(round(secs * 1000))))
            at += secs
        done += 1
        if loops == 0 or done < loops:
            at += pause


def repeats_for(one, pause, loops=1, min_seconds=None):
    """How many times an export repeats: `loops`, or (if min_seconds is given) enough whole repeats to reach it."""
    if min_seconds:
        n = max(1, math.ceil((min_seconds + pause) / (one + pause)))
    else:
        n = max(1, loops)
    while n > 1 and n * one + (n - 1) * pause > MAX_EXPORT_SECONDS:
        n -= 1
    return n


def render_wav(text, wpm, hz, path, rate=44100, fwpm=None, loops=1, min_seconds=None):
    """Write the Morse as a WAV file (mono, 16-bit) with the same timing as play(). Returns its length in seconds.

    loops = how many times the message repeats; or min_seconds = repeat (whole messages only) until the file is at least
    that long. Each tone fades in and out over 5 ms so there are no clicks; there is a short silence at each end."""
    import wave

    import numpy as np

    tl, pause = timeline(text, wpm, fwpm), loop_pause(wpm, fwpm)
    one = sum(s for _, s in tl)
    n = repeats_for(one, pause, loops, min_seconds)
    lead, tail = int(0.2 * rate), int(0.4 * rate)
    audio = np.zeros(lead + int(round((n * one + (n - 1) * pause) * rate)) + tail, np.float32)
    at = 0.0
    for _ in range(n):
        for on, secs in tl:
            if on:
                start, count = lead + int(round(at * rate)), int(round(secs * rate))
                env = np.ones(count, np.float32)
                ramp = min(int(0.005 * rate), count // 2)
                env[:ramp] = 0.5 - 0.5 * np.cos(np.pi * np.arange(ramp) / ramp)
                env[count - ramp:] = env[:ramp][::-1]
                audio[start:start + count] = np.sin(2 * np.pi * hz * np.arange(count) / rate) * env
            at += secs
        at += pause
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((audio * 0.6 * 32767).astype("<i2").tobytes())
    return len(audio) / rate


def selftest() -> int:
    bad = 0

    def check(ok, what):
        nonlocal bad
        print(("PASS " if ok else "FAIL ") + what)
        bad += (not ok)

    check(encode("PARIS") == ".--. .- .-. .. ...", "PARIS = .--. .- .-. .. ...")
    check(encode("SOS") == "... --- ..." and encode("73") == "--... ...--", "SOS and 73")
    check(encode("HI DAD") == ".... .. / -.. .- -..", "words are separated by ' / '")
    check(encode("A#B") == ".- -...", "characters with no code are skipped")
    check(schedule("E") == [(True, 1)] and schedule("T") == [(True, 3)], "a dit is 1 unit, a dah is 3")
    total = sum(u for _, u in schedule("PARIS")) + 7  # the word plus its trailing word gap
    check(total == 50, f"PARIS plus the word gap is exactly 50 dits (got {total}): the definition of WPM")
    check(schedule("A B") == [(True, 1), (False, 1), (True, 3), (False, 7), (True, 3), (False, 1), (True, 1),
                              (False, 1), (True, 1), (False, 1), (True, 1)],
          "gaps: 1 within a letter, 7 between words")
    codes = list(MORSE.values())
    check(len(set(codes)) == len(codes), "no two characters share a code")
    check(all(c in MORSE for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), "all 26 letters and 10 digits are present")

    # Farnsworth spacing
    same = timeline("PARIS", 20)
    check(all(abs(s - u * 0.06) < 1e-12 for (_, s), (_, u) in zip(same, schedule("PARIS"))) and
          timeline("PARIS", 20, 20) == same and timeline("PARIS", 20, 30) == same,
          "no Farnsworth (or an overall speed at or above the letter speed) leaves the timing alone")
    far = timeline("PARIS", 20, 10)
    word = sum(s for _, s in far) + 7 * spacing(20, 10)
    check(abs(word - 6.0) < 1e-9, f"PARIS at 20 WPM letters, 10 WPM overall takes {word:.3f} s = 60/10 (the definition)")
    check(all(abs(s - 0.06 * u) < 1e-12 for (on, s), (_, u) in zip(far, schedule("PARIS")) if on or u == 1),
          "Farnsworth keeps every tone and every gap inside a letter at full speed")

    import os
    import tempfile
    import wave

    import numpy as np

    def tones_of(path):
        with wave.open(path, "rb") as w:
            rate, chans, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            pcm = np.frombuffer(w.readframes(frames), "<i2").astype(np.float32) / 32768.0
        env = np.abs(pcm)
        peak = np.maximum.reduceat(env, np.arange(0, len(env), 200))  # a sine crosses zero: use a small window's peak
        on = peak > 0.15
        return (rate, chans, width, frames), pcm, int(on[0]) + int((on[1:] & ~on[:-1]).sum())

    path = os.path.join(tempfile.gettempdir(), "morse_selftest.wav")
    seconds = render_wav("PARIS", 20, 700, path)
    (rate, chans, width, frames), pcm, tones = tones_of(path)
    ideal = 43 * 0.06 + 0.2 + 0.4  # PARIS at 20 WPM is 43 dits of 60 ms, plus the lead and tail silence
    check((rate, chans, width) == (44100, 1, 2), "WAV: 44100 Hz, mono, 16-bit")
    check(abs(frames / rate - ideal) < 0.01 and abs(seconds - ideal) < 0.01,
          f"WAV length {frames / rate:.3f} s matches the timing ({ideal:.3f} s)")
    check(tones == 14, f"WAV holds exactly the 14 tones of PARIS (found {tones})")
    check(0.5 < np.abs(pcm).max() <= 0.62 and np.abs(pcm[:int(0.15 * rate)]).max() == 0, "WAV: sensible volume, silent lead-in")

    one, pause = sum(s for _, s in timeline("PARIS", 20, 10)), loop_pause(20, 10)
    seconds = render_wav("PARIS", 20, 700, path, fwpm=10, loops=3)
    (_, _, _, frames), _, tones = tones_of(path)
    check(abs(seconds - (0.6 + 3 * one + 2 * pause)) < 0.01 and tones == 42,
          f"3 loops with Farnsworth: {seconds:.2f} s long with 42 tones (3 x 14)")
    seconds = render_wav("SOS", 20, 700, path, min_seconds=30)
    n = repeats_for(sum(s for _, s in timeline("SOS", 20)), loop_pause(20), 1, 30)
    _, _, tones = tones_of(path)
    check(seconds - 0.6 >= 30 and seconds - 0.6 - (sum(s for _, s in timeline("SOS", 20)) + loop_pause(20)) < 30 and
          tones == 9 * n, f"export 'at least 30 s': {seconds - 0.6:.1f} s in {n} whole repeats (one fewer would be short)")
    check(repeats_for(10.0, 2.0, 1, 999999) * 12 - 2 <= MAX_EXPORT_SECONDS, "an export is capped at half an hour")
    os.remove(path)

    print("ALL PASSED" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


def window():
    import tkinter as tk

    root = tk.Tk()
    root.title("Morse code - Bordeom")
    root.resizable(False, False)
    stop = threading.Event()
    state = {"thread": None}
    hide = tk.BooleanVar(value=False)

    box = tk.Text(root, width=52, height=4, font=("Consolas", 14), wrap="word")
    box.insert("1.0", "CQ CQ")
    box.grid(row=0, column=0, columnspan=8, padx=8, pady=(8, 4))
    dots = tk.Label(root, text="", font=("Consolas", 11), wraplength=640, justify="left", anchor="w")
    dots.grid(row=1, column=0, columnspan=8, sticky="we", padx=8)

    def spin(row, col, label, lo, hi, value, width=5, step=1):
        tk.Label(root, text=label).grid(row=row, column=col, padx=(10, 2), pady=4, sticky="e")
        s = tk.Spinbox(root, from_=lo, to=hi, increment=step, width=width, font=("Consolas", 12))
        s.delete(0, "end")
        s.insert(0, value)
        s.grid(row=row, column=col + 1, sticky="w")
        return s

    letters = spin(2, 0, "Letter speed (WPM)", 5, 40, "12")
    overall = spin(2, 2, "Overall (WPM, blank = same)", 3, 40, "")
    tone = spin(2, 4, "Tone (Hz)", 300, 1200, "600", step=50)
    repeat = spin(3, 0, "Repeats (0 = until Stop)", 0, 999, "1")
    fill = spin(3, 2, "Export at least (seconds, 0 = off)", 0, MAX_EXPORT_SECONDS, "0", step=30)
    tk.Checkbutton(root, text="Hide dots and dashes (listen first)", variable=hide).grid(
        row=3, column=4, columnspan=3, sticky="w", padx=10)

    def number(widget, default, lo, hi):
        try:
            return max(lo, min(hi, int(widget.get())))
        except ValueError:
            return default

    def settings():
        wpm = number(letters, 12, 5, 40)
        fwpm = number(overall, wpm, 3, 40) if overall.get().strip() else wpm
        return wpm, min(fwpm, wpm), number(tone, 600, 200, 2000)

    def show_dots():
        dots.config(text=encode(box.get("1.0", "end")) or "(nothing I can send)")

    def go(_event=None):
        stop.set()  # stop anything still playing, then start fresh
        if state["thread"] is not None:
            state["thread"].join(timeout=2)
        text = box.get("1.0", "end").strip()
        if hide.get():
            dots.config(text="(hidden: listen first, then press Reveal)" if encode(text) else "(nothing I can send)")
        else:
            show_dots()
        stop.clear()
        wpm, fwpm, hz = settings()
        state["thread"] = threading.Thread(
            target=play, args=(text, wpm, hz, stop, fwpm, number(repeat, 1, 0, 999)), daemon=True)
        state["thread"].start()
        return "break"

    def save():
        from tkinter import filedialog

        text = box.get("1.0", "end").strip()
        if not encode(text):
            dots.config(text="(nothing I can send)")
            return
        path = filedialog.asksaveasfilename(parent=root, defaultextension=".wav", filetypes=[("WAV audio", "*.wav")],
                                            initialfile="morse.wav", title="Save the Morse as audio")
        if path:
            wpm, fwpm, hz = settings()
            secs = number(fill, 0, 0, MAX_EXPORT_SECONDS)
            seconds = render_wav(text, wpm, hz, path, fwpm=fwpm, loops=max(1, number(repeat, 1, 0, 999)),
                                 min_seconds=secs or None)
            dots.config(text=f"Saved {seconds:.1f} s of audio: {path}")

    tk.Button(root, text="Save WAV...", width=12, font=("Segoe UI", 10), command=save).grid(
        row=4, column=0, columnspan=2, padx=8, pady=8, sticky="w")
    tk.Button(root, text="Reveal", width=8, font=("Segoe UI", 11), command=show_dots).grid(row=4, column=4, pady=8)
    tk.Button(root, text="Go", width=8, font=("Segoe UI", 12, "bold"), command=go).grid(row=4, column=5, padx=6)
    tk.Button(root, text="Stop", width=8, font=("Segoe UI", 12), command=stop.set).grid(row=4, column=6, padx=(0, 8))
    box.bind("<Control-Return>", go)
    box.focus_set()
    root.protocol("WM_DELETE_WINDOW", lambda: (stop.set(), root.destroy()))
    root.mainloop()


def main() -> int:
    ap = argparse.ArgumentParser(description="Type text, hear Morse code")
    ap.add_argument("text", nargs="*", help="what to send; leave empty for the window")
    ap.add_argument("--wpm", type=int, default=12, help="speed of the letters, in words per minute")
    ap.add_argument("--fwpm", type=int, default=None, help="overall speed (Farnsworth): longer gaps if below --wpm")
    ap.add_argument("--hz", type=int, default=600)
    ap.add_argument("--loops", type=int, default=1, help="repeat this many times; 0 = until Ctrl+C (playing only)")
    ap.add_argument("--save", metavar="FILE.wav", help="write the audio to a WAV file instead of playing it")
    ap.add_argument("--seconds", type=int, default=None, help="with --save: repeat until the file is at least this long")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.text:
        text = " ".join(args.text)
        print(encode(text))
        if args.save:
            secs = render_wav(text, args.wpm, args.hz, args.save, fwpm=args.fwpm, loops=max(1, args.loops),
                              min_seconds=args.seconds)
            print(f"saved {secs:.1f} s of audio to {args.save}")
        else:
            try:
                play(text, args.wpm, args.hz, fwpm=args.fwpm, loops=args.loops)
            except KeyboardInterrupt:
                pass
        return 0
    window()
    return 0


if __name__ == "__main__":
    sys.exit(main())
