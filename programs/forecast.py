#!/usr/bin/env python3
"""
Pocket Forecast -- textbook single-station weather prediction.

A Bordeom program: what a 1990s DOS toy looks like today.

You enter the basic observations any weather watcher can make from a porch --
barometer reading and its trend, wind direction, the look of the sky -- and
the program answers the way the old textbook said to: a simplified version of
the Zambretti method (the 1915 barometer forecaster) plus the classic
cloud-progression rules.

Optionally, pick a date and it will also pull public data for that date from
Open-Meteo (which republishes national weather-service data, no key needed):
what actually happened for a past date, or the model forecast for a future
one, so you can hold the textbook up against the computers.

Pure standard library -- nothing to install.
Run:  python forecast.py            (interactive)
      python forecast.py 2026-11-01 (straight to a date lookup)
      python forecast.py --selftest (headless self-check)
"""

import json
import sys
import urllib.request
from datetime import date, datetime, timedelta

# Default station: Defiance, Ohio. Change at the prompt if you like.
DEFAULT_LAT = 41.2845
DEFAULT_LON = -84.3558
DEFAULT_TZ = "America/New_York"

WINDS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "CALM"]
WIND_SCORE = {"N": 6, "NE": 6, "E": 2, "SE": -4, "S": -6,
              "SW": -2, "W": 3, "NW": 5, "CALM": 0}

TRENDS = ["rising fast", "rising", "steady", "falling", "falling fast"]
TREND_SCORE = {"rising fast": 15, "rising": 8, "steady": 0,
               "falling": -8, "falling fast": -18}

SKIES = {
    "1": ("clear", "Clear / mostly clear"),
    "2": ("scattered", "Scattered puffy clouds (fair-weather cumulus)"),
    "3": ("towering", "Towering cumulus / building thunderheads"),
    "4": ("cirrus", "High thin cirrus (mare's tails)"),
    "5": ("sheet", "Gray sheet covering the sun (altostratus)"),
    "6": ("overcast", "Broken to solid overcast, no rain yet"),
    "7": ("fog", "Fog or low mist"),
    "8": ("rain", "Raining now"),
    "9": ("snow", "Snowing now"),
}

VERDICTS = [
    (80, "Settled fine."),
    (68, "Fine, becoming less settled."),
    (56, "Fair, possible showers later."),
    (45, "Changeable, some rain."),
    (34, "Unsettled, rain at times."),
    (22, "Rainy, possibly windy."),
    (-10 ** 9, "Stormy, much rain."),
]


def to_hpa(value):
    """Accept a pressure in inHg (e.g. 29.92) or hPa (e.g. 1013), return hPa."""
    if value < 50:            # clearly inches of mercury
        return value * 33.8639
    return value              # already hPa / millibars


def predict(pressure_hpa, trend, wind, sky, humid):
    """The textbook. Returns (headline, [note lines])."""
    # Base score: pressure mapped onto 0..100 across 980..1040 hPa.
    score = (pressure_hpa - 980) * (100.0 / 60.0)
    score += TREND_SCORE[trend]
    score += WIND_SCORE[wind]
    score = max(0.0, min(100.0, score))

    headline = next(text for floor, text in VERDICTS if score >= floor)
    notes = []

    # Classic cloud-progression rules, layered over the barometer verdict.
    if sky == "cirrus" and trend.startswith("falling"):
        notes.append("Textbook: cirrus thickening with a falling glass means "
                     "a warm front is coming -- rain likely within about 24 hours.")
    elif sky == "cirrus":
        notes.append("Textbook: high cirrus alone often just means change is "
                     "on the way in a day or two. Watch whether it thickens.")
    if sky == "sheet":
        notes.append("Textbook: a gray sheet over the sun is the front's "
                     "doorstep -- rain likely within about 12 hours.")
    if sky == "towering" and humid:
        notes.append("Textbook: thunderheads building in humid air -- "
                     "thunderstorms possible this afternoon or evening.")
    elif sky == "towering":
        notes.append("Textbook: cumulus growing tall bears watching; "
                     "showers possible if it keeps building.")
    if sky == "fog" and not trend.startswith("falling"):
        notes.append("Textbook: fog with a steady or rising glass usually "
                     "burns off by midday, then fair.")
    if sky == "rain" and trend == "falling fast":
        notes.append("Textbook: rain with a fast-falling glass is not "
                     "leaving soon -- possibly heavy at times.")
    if sky == "snow":
        notes.append("Textbook: read the verdict above as snow amounts "
                     "rather than rain.")
    if wind != "CALM":
        notes.append("Buys-Ballot: stand with your back to the wind and the "
                     "low pressure is on your left (northern hemisphere).")

    return headline, notes, round(score)


# --------------------------------------------------------------------------
# Public data: Open-Meteo archive (past) and forecast (future). No key.
# --------------------------------------------------------------------------

def fetch_day(lat, lon, tz, when):
    today = date.today()
    if when < today:
        base = "https://archive-api.open-meteo.com/v1/archive"
    else:
        base = "https://api.open-meteo.com/v1/forecast"
    url = (f"{base}?latitude={lat}&longitude={lon}"
           f"&start_date={when.isoformat()}&end_date={when.isoformat()}"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
           "wind_speed_10m_max&temperature_unit=fahrenheit"
           "&wind_speed_unit=mph&precipitation_unit=inch"
           f"&timezone={urllib.request.quote(tz, safe='')}")
    req = urllib.request.Request(url, headers={"User-Agent": "PocketForecast/1.0"})
    last_exc = None
    for attempt in range(2):  # one polite retry; public APIs throttle sometimes
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                import time
                time.sleep(6)
    else:
        raise last_exc
    daily = data.get("daily", {})
    out = {}
    for key in ("temperature_2m_max", "temperature_2m_min",
                "precipitation_sum", "wind_speed_10m_max"):
        vals = daily.get(key) or [None]
        out[key] = vals[0]
    return out


def show_day(lat, lon, tz, when):
    today = date.today()
    kind = "actually did" if when < today else "the models say will do"
    print(f"\n--- {when.isoformat()} ({when.strftime('%A')}) ---")
    print(f"For {lat:.4f}, {lon:.4f}, here is what that day {kind}:")
    try:
        d = fetch_day(lat, lon, tz, when)
    except Exception as exc:  # offline, out of range, API grumpy
        print(f"  Could not fetch public data: {exc}")
        print("  (Future dates reach about 16 days out; the archive "
              "goes back to 1940.)")
        return
    def fmt(v, unit):
        return f"{v:g}{unit}" if v is not None else "n/a"
    print(f"  High:        {fmt(d['temperature_2m_max'], ' F')}")
    print(f"  Low:         {fmt(d['temperature_2m_min'], ' F')}")
    print(f"  Precip:      {fmt(d['precipitation_sum'], ' in')}")
    print(f"  Top wind:    {fmt(d['wind_speed_10m_max'], ' mph')}")
    print("  Source: Open-Meteo (national weather-service data, public).")


# --------------------------------------------------------------------------
# The porch form
# --------------------------------------------------------------------------

def ask(prompt, valid=None, default=None):
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        if valid is None or raw.lower() in valid:
            return raw
        print(f"  Please answer one of: {', '.join(valid)}")


def ask_float(prompt):
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("  Numbers only, please.")


def observation_form():
    print("\n--- Your observations ---")
    p = ask_float("Barometer now (inHg like 29.92, or hPa like 1013): ")
    pressure = to_hpa(p)
    print(f"  = {pressure:.0f} hPa")
    print("Barometer trend over the last few hours:")
    for i, t in enumerate(TRENDS, 1):
        print(f"  {i}. {t}")
    trend = TRENDS[int(ask("Trend number: ", valid={str(i) for i in range(1, 6)})) - 1]
    wind = ask("Wind direction (N NE E SE S SW W NW, or CALM): ",
               valid={w.lower() for w in WINDS}).upper()
    print("Sky:")
    for key, (_, label) in SKIES.items():
        print(f"  {key}. {label}")
    sky = SKIES[ask("Sky number: ", valid=set(SKIES))][0]
    humid = ask("Does the air feel humid? (y/n): ", valid={"y", "n"}) == "y"

    headline, notes, score = predict(pressure, trend, wind, sky, humid)
    print("\n--- Textbook prediction ---")
    print(f"  {headline}")
    for note in notes:
        print(f"  {note}")
    print(f"  (Forecaster score {score}/100 from {pressure:.0f} hPa, "
          f"{trend}, wind {wind}.)")


def parse_date(text):
    return datetime.strptime(text, "%Y-%m-%d").date()


def main(argv):
    if "--selftest" in argv:
        return selftest()
    print("POCKET FORECAST -- the textbook weather glass, in a program.")
    print("Default station: Defiance, Ohio (41.2845, -84.3558).")
    lat, lon, tz = DEFAULT_LAT, DEFAULT_LON, DEFAULT_TZ

    args = [a for a in argv if not a.startswith("-")]
    if args:
        try:
            show_day(lat, lon, tz, parse_date(args[0]))
            return 0
        except ValueError:
            print(f"Could not read '{args[0]}' as a date (use YYYY-MM-DD).")
            return 1

    while True:
        print("\n1. Enter observations -> textbook prediction")
        print("2. Look up a date (past = what happened, future = model forecast)")
        print("3. Quit")
        choice = ask("Choice: ", valid={"1", "2", "3"})
        if choice == "1":
            observation_form()
        elif choice == "2":
            raw = input("Date (YYYY-MM-DD): ").strip()
            try:
                when = parse_date(raw)
            except ValueError:
                print("  Use YYYY-MM-DD, e.g. 2026-11-01.")
                continue
            if when > date.today() + timedelta(days=16):
                print("  The model forecast only reaches about 16 days out.")
                continue
            show_day(lat, lon, tz, when)
        else:
            print("Clear skies.")
            return 0


def selftest():
    checks = []

    def check(name, ok):
        checks.append((name, ok))
        print(f"  {'ok ' if ok else 'FAIL'}  {name}")

    check("inHg converts to hPa", abs(to_hpa(29.92) - 1013.2) < 1.0)
    check("hPa passes through", to_hpa(1013) == 1013)

    h, _, s = predict(1030, "rising", "NW", "clear", False)
    check("high & rising & NW = settled fine", h.startswith("Settled") and s >= 80)
    h, _, s = predict(990, "falling fast", "S", "rain", True)
    check("low & falling fast & S = stormy", h.startswith("Stormy") and s < 22)
    h, n, _ = predict(1008, "falling", "SW", "cirrus", False)
    check("cirrus + falling glass = 24h rain note",
          any("24 hours" in line for line in n))
    h, n, _ = predict(1015, "steady", "CALM", "sheet", False)
    check("gray sheet = 12h rain note", any("12 hours" in line for line in n))
    h, n, _ = predict(1005, "steady", "S", "towering", True)
    check("towering + humid = thunderstorm note",
          any("thunderstorms possible" in line for line in n))
    check("date parses", parse_date("2026-11-01") == date(2026, 11, 1))

    failed = [n for n, ok in checks if not ok]
    print(f"selftest: {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
