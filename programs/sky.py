"""Bordeom / sky.py -- what's up tonight? A backyard-telescope sky guide.

Approximate positions (good enough for a finder scope, not for astrometry): the Sun, Moon and
8 planets from low-precision orbital elements, 95 showpiece deep-sky objects and 25 bright
stars, plotted on an all-sky chart with an "up now" list, rise/transit/set times, and a red
night-vision mode that won't wreck your dark adaptation.

    python sky.py                          # live sky, default site (40N 86W)
    python sky.py --lat 40.7 --lon -74.0   # your backyard (look it up on a map)
    python sky.py --at "2026-11-14 21:00"  # plan ahead (local time)
    python sky.py --selftest               # headless checks, no window

Keys:  Left/Right = -/+ 1 hour    Up/Down = -/+ 1 day    Home or 0 = back to now
       Tab / Shift+Tab = pick object    click = pick object    R = red night mode
       Space = pause time     F or Enter = fullscreen     S = save a screenshot
       H = hide/show help     Esc or Q = quit
"""

import argparse
import datetime as dt
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D2R = math.pi / 180.0
R2D = 180.0 / math.pi


# -- Angles and time ----------------------------------------------------------------------------
def rev(x: float) -> float:
    """Any angle -> 0..360."""
    return x % 360.0


def sind(x: float) -> float:
    return math.sin(x * D2R)


def cosd(x: float) -> float:
    return math.cos(x * D2R)


def tand(x: float) -> float:
    return math.tan(x * D2R)


def atan2d(y: float, x: float) -> float:
    return math.atan2(y, x) * R2D


def asind(x: float) -> float:
    return math.asin(max(-1.0, min(1.0, x))) * R2D


def acosd(x: float) -> float:
    return math.acos(max(-1.0, min(1.0, x))) * R2D


def to_jd(moment: dt.datetime) -> float:
    """Aware datetime -> Julian day (Meeus). 2000-01-01 12:00 UTC is 2451545.0."""
    u = moment.astimezone(dt.timezone.utc)
    y, m, day = u.year, u.month, u.day
    a = (14 - m) // 12
    y, m = y + 4800 - a, m + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn + (u.hour - 12) / 24.0 + u.minute / 1440.0 + (u.second + u.microsecond / 1e6) / 86400.0


def from_jd(jd: float) -> dt.datetime:
    """Julian day -> aware UTC datetime."""
    return dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc) + dt.timedelta(days=jd - 2451545.0)


def gmst_deg(jd: float) -> float:
    """Greenwich Mean Sidereal Time in degrees."""
    t = (jd - 2451545.0) / 36525.0
    return rev(280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t
               - t * t * t / 38710000.0)


def parse_when(text: str, now: dt.datetime) -> dt.datetime:
    """"YYYY-MM-DD HH:MM", "YYYY-MM-DD" or "HH:MM" (local) -> aware datetime."""
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=now.tzinfo)
        except ValueError:
            pass
    t = dt.datetime.strptime(text, "%H:%M").time()
    return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


# -- Orbits (low-precision elements, Paul Schlyter's longitudes: good to arcminutes) ------------
# (N0,Ndot, i0,idot, w0,wdot, a0,adot, e0,edot, M0,Mdot), d = days since 2000 Jan 0.0 (= JD 2451543.5)
ELEMENTS = {
    "Earth":   (0.0, 0.0, 0.0, 0.0, 282.9404, 4.70935e-5, 1.000000, 0.0, 0.016709, -1.151e-9,
                356.0470, 0.9856002585),
    "Moon":    (125.1228, -0.0529538083, 5.1454, 0.0, 318.0634, 0.1643573223, 60.2666, 0.0,
                0.054900, 0.0, 115.3654, 13.0649929509),
    "Mercury": (48.3313, 3.24587e-5, 7.0047, 5.00e-8, 29.1241, 1.01444e-5, 0.387098, 0.0,
                0.205635, 5.59e-10, 168.6562, 4.0923344368),
    "Venus":   (76.6799, 2.46590e-5, 3.3946, 2.75e-8, 54.8910, 1.38374e-5, 0.723330, 0.0,
                0.006773, -1.302e-9, 48.0052, 1.6021304744),
    "Mars":    (49.5574, 2.11081e-5, 1.8497, -1.78e-8, 286.5016, 2.92961e-5, 1.523688, 0.0,
                0.093405, 2.516e-9, 18.6021, 0.5240207766),
    "Jupiter": (100.4542, 2.76854e-5, 1.3030, -1.557e-7, 273.8777, 1.64505e-5, 5.20256, 0.0,
                0.048498, 4.469e-9, 19.8950, 0.0830853001),
    "Saturn":  (113.6634, 2.38980e-5, 2.4886, -1.081e-7, 339.3939, 2.97661e-5, 9.55475, 0.0,
                0.055546, -9.499e-9, 316.9670, 0.0334442282),
    "Uranus":  (74.0005, 1.3978e-5, 0.7733, 1.9e-8, 96.6612, 3.0565e-5, 19.18171, -1.55e-8,
                0.047318, 7.45e-9, 142.5905, 0.011725806),
    "Neptune": (131.7806, 3.0173e-5, 1.7700, -2.55e-7, 272.8461, -6.027e-6, 30.05826, 3.313e-8,
                0.008606, 2.15e-9, 260.2471, 0.005995147),
}


def kepler(m_deg: float, e: float) -> float:
    """Mean anomaly -> eccentric anomaly (degrees), by iteration."""
    m = m_deg * D2R
    en = m + e * math.sin(m)
    for _ in range(8):
        en = en - (en - e * math.sin(en) - m) / (1 - e * math.cos(en))
    return en * R2D


def helio(name: str, d: float) -> dict:
    """Heliocentric ecliptic position: rectangular + (lon, lat, r) + mean anomaly."""
    n0, nd, i0, id_, w0, wd, a0, ad, e0, ed, m0, md = ELEMENTS[name]
    n, i, w = rev(n0 + nd * d), i0 + id_ * d, rev(w0 + wd * d)
    a, e, m = a0 + ad * d, e0 + ed * d, rev(m0 + md * d)
    en = kepler(m, e) * D2R
    x, y = a * (math.cos(en) - e), a * math.sqrt(1 - e * e) * math.sin(en)
    r, v = math.hypot(x, y), math.atan2(y, x) * R2D
    xh = r * (cosd(n) * cosd(v + w) - sind(n) * sind(v + w) * cosd(i))
    yh = r * (sind(n) * cosd(v + w) + cosd(n) * sind(v + w) * cosd(i))
    zh = r * sind(v + w) * sind(i)
    return {"x": xh, "y": yh, "z": zh, "r": r, "lon": rev(atan2d(yh, xh)),
            "lat": atan2d(zh, math.hypot(xh, yh)), "M": m, "N": n, "w": w}


def obliquity(d: float) -> float:
    return 23.4393 - 3.563e-7 * d


def precess(ra_h: float, dec_d: float, jd_from: float, jd_to: float) -> tuple:
    """Precess RA/Dec between epochs (Meeus low accuracy, good for centuries around J2000)."""
    t = (jd_to - jd_from) / 36525.0
    zeta = (2306.2181 * t + 0.30188 * t * t + 0.017998 * t * t * t) / 3600.0
    z = (2306.2181 * t + 1.09468 * t * t + 0.018203 * t * t * t) / 3600.0
    theta = (2004.3109 * t - 0.42665 * t * t - 0.041833 * t * t * t) / 3600.0
    a = ra_h * 15.0 + zeta
    A = cosd(dec_d) * sind(a)
    B = cosd(theta) * cosd(dec_d) * cosd(a) - sind(theta) * sind(dec_d)
    C = sind(theta) * cosd(dec_d) * cosd(a) + cosd(theta) * sind(dec_d)
    return rev(atan2d(A, B) + z) / 15.0, asind(C)


def ecl_to_eq(lon: float, lat: float, d: float) -> tuple:
    """Ecliptic degrees -> (RA hours, Dec degrees)."""
    e = obliquity(d)
    ra = rev(atan2d(sind(lon) * cosd(e) - tand(lat) * sind(e), cosd(lon))) / 15.0
    dec = asind(sind(lat) * cosd(e) + cosd(lat) * sind(e) * sind(lon))
    return ra, dec


def earth_helio(d: float) -> dict:
    """True heliocentric Earth: Schlyter's Earth row yields Sun-geocentric coords, so negate."""
    h = helio("Earth", d)
    return {"x": -h["x"], "y": -h["y"], "z": -h["z"], "r": h["r"], "M": h["M"], "w": h["w"]}


def sun_geo(d: float) -> dict:
    """Geocentric Sun: the Earth row's lon/lat already are the Sun's apparent place (no +180)."""
    e = helio("Earth", d)
    ra, dec = ecl_to_eq(e["lon"], e["lat"], d)
    return {"ra": ra, "dec": dec, "r": e["r"], "M": e["M"], "lon": e["lon"], "lat": e["lat"]}


def moon_geo(d: float, sun: dict) -> dict:
    """Geocentric Moon with the major perturbation terms (else it wanders by degrees)."""
    mo = helio("Moon", d)
    ms, mm = sun["M"], mo["M"]
    lm = rev(mo["N"] + mo["w"] + mm)          # mean longitude
    ls = rev(helio("Earth", d)["w"] + ms)     # sun's mean longitude
    elong, f = rev(lm - ls), rev(lm - mo["N"])  # mean elongation, argument of latitude
    lon = (mo["lon"] - 1.274 * sind(mm - 2 * elong) + 0.658 * sind(2 * elong)
           - 0.186 * sind(ms) - 0.059 * sind(2 * mm - 2 * elong)
           - 0.057 * sind(mm - 2 * elong + ms) + 0.053 * sind(mm + 2 * elong)
           + 0.046 * sind(2 * elong - ms) + 0.041 * sind(mm - ms) - 0.035 * sind(elong)
           - 0.031 * sind(mm + ms) - 0.015 * sind(2 * f - 2 * elong)
           + 0.011 * sind(mm - 4 * elong))
    lat = (mo["lat"] - 0.173 * sind(f - 2 * elong) - 0.055 * sind(mm - f - 2 * elong)
           - 0.046 * sind(mm + f - 2 * elong) + 0.033 * sind(f + 2 * elong)
           + 0.017 * sind(2 * mm + f))
    r = mo["r"] - 0.58 * cosd(mm - 2 * elong) - 0.46 * cosd(2 * elong)  # earth radii
    ra, dec = ecl_to_eq(lon, lat, d)
    return {"ra": ra, "dec": dec, "r": r, "lon": rev(lon), "lat": lat}


def planet_geo(name: str, d: float, earth: dict) -> dict:
    """Geocentric planet: RA/Dec, distances, phase angle and approximate magnitude."""
    p = helio(name, d)
    xg, yg, zg = p["x"] - earth["x"], p["y"] - earth["y"], p["z"] - earth["z"]
    delta = math.sqrt(xg * xg + yg * yg + zg * zg)  # earth distance, AU
    lon = rev(atan2d(yg, xg))
    if name in ("Jupiter", "Saturn"):  # the great inequality (0.3 / 0.8 deg); smaller terms skipped
        mj = helio("Jupiter", d)["M"]
        ms = helio("Saturn", d)["M"]
        g = mj * 2 - ms * 5 - 67.6
        lon += (-0.332 * sind(g) - 0.056 * sind(2 * mj - 2 * ms + 21.0)
                + 0.042 * sind(3 * mj - 5 * ms + 21.0)) if name == "Jupiter" else 0.812 * sind(g)
    ra, dec = ecl_to_eq(lon, atan2d(zg, math.hypot(xg, yg)), d)
    fv = acosd((p["r"] ** 2 + delta ** 2 - earth["r"] ** 2) / (2 * p["r"] * delta))  # phase angle
    mag = {"Mercury": -0.42 + 5 * math.log10(p["r"] * delta) + 0.0380 * fv - 0.000273 * fv * fv,
           "Venus": -4.40 + 5 * math.log10(p["r"] * delta) + 0.0009 * fv + 0.000239 * fv * fv,
           "Mars": -1.52 + 5 * math.log10(p["r"] * delta) + 0.016 * fv,
           "Jupiter": -9.40 + 5 * math.log10(p["r"] * delta) + 0.005 * fv,
           "Saturn": -8.68 + 5 * math.log10(p["r"] * delta) + 0.044 * fv,  # rings ignored: ~0.5 mag off
           "Uranus": -7.19 + 5 * math.log10(p["r"] * delta),
           "Neptune": -6.87 + 5 * math.log10(p["r"] * delta)}[name]
    return {"ra": ra, "dec": dec, "r": p["r"], "delta": delta, "mag": mag}


# -- Looking up ---------------------------------------------------------------------------------
def altaz(ra_h: float, dec_d: float, lat: float, lon: float, jd: float) -> tuple:
    """RA/Dec -> (altitude, azimuth from North going East), degrees. lon is East-positive."""
    ha = rev(gmst_deg(jd) + lon - ra_h * 15.0)
    alt = asind(sind(dec_d) * sind(lat) + cosd(dec_d) * cosd(lat) * cosd(ha))
    az = rev(atan2d(sind(ha), cosd(ha) * sind(lat) - tand(dec_d) * cosd(lat)))
    return alt, az


def separation(ra1: float, dc1: float, ra2: float, dc2: float) -> float:
    """Angular separation of two RA/Dec points, degrees."""
    return acosd(sind(dc1) * sind(dc2) + cosd(dc1) * cosd(dc2) * cosd((ra1 - ra2) * 15.0))


COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass(az: float) -> str:
    return COMPASS16[int(rev(az + 11.25) // 22.5) % 16]


def moon_phase(jd: float) -> tuple:
    """(illumination 0..1, phase name) from the Sun-Moon separation."""
    d = jd - 2451543.5
    sun, moon = sun_geo(d), moon_geo(d, sun_geo(d))
    sep = separation(sun["ra"], sun["dec"], moon["ra"], moon["dec"])
    d2 = jd + 1.0 - 2451543.5
    sun2, moon2 = sun_geo(d2), moon_geo(d2, sun_geo(d2))
    waxing = separation(sun2["ra"], sun2["dec"], moon2["ra"], moon2["dec"]) > sep
    age = sep / 12.19 if waxing else 29.53 - sep / 12.19  # synodic month, roughly
    names = ["New", "Waxing crescent", "First quarter", "Waxing gibbous",
             "Full", "Waning gibbous", "Last quarter", "Waning crescent"]
    return (1 - cosd(sep)) / 2, names[int(((age % 29.53) + 29.53) % 29.53 // 3.69) % 8]


def alt_series(radec, lat: float, lon: float, jd0: float, span_days: float = 1.0,
               step_min: float = 2.0) -> tuple:
    """Altitudes of a fixed RA/Dec (or callable jd -> (ra, dec)) across a window. numpy does the loop."""
    n = int(span_days * 24 * 60 / step_min) + 1
    jds = np.linspace(jd0 - span_days / 2, jd0 + span_days / 2, n)
    if callable(radec):
        radecs = [radec(j) for j in jds]
    else:
        radecs = [radec] * n
    alts = np.array([altaz(ra, dc, lat, lon, j)[0] for (ra, dc), j in zip(radecs, jds)])
    return jds, alts


def events(radec, lat: float, lon: float, jd0: float, horizon: float = 0.0) -> dict:
    """Rise/transit/set nearest jd0 by scanning a day. Flags: ok / up-all-day / never-rises."""
    jds, alts = alt_series(radec, lat, lon, jd0)
    above = alts > horizon
    if above.all():
        return {"flag": "up-all-day", "rise": None, "transit": from_jd(jds[int(np.argmax(alts))]),
                "set": None}
    if not above.any():
        return {"flag": "never-rises", "rise": None, "transit": None, "set": None}
    cross = np.where(np.diff(above))[0]
    best = {"flag": "ok", "rise": None, "transit": from_jd(jds[int(np.argmax(alts))]), "set": None}
    for k in cross:  # linear interpolation to the crossing moment
        f = (horizon - alts[k]) / (alts[k + 1] - alts[k])
        t = from_jd(jds[k] + f * (jds[k + 1] - jds[k]))
        key = "rise" if alts[k + 1] > alts[k] else "set"
        if best[key] is None or abs((t - from_jd(jd0)).total_seconds()) < abs(
                (best[key] - from_jd(jd0)).total_seconds()):
            best[key] = t
    return best


def sun_events(lat: float, lon: float, jd0: float) -> dict:
    """Sunset/sunrise plus the starts/ends of astronomical darkness, nearest jd0."""
    out = {}
    for key, level in (("sunset", -0.833), ("sunrise", -0.833),
                       ("astro_dusk", -18.0), ("astro_dawn", -18.0),
                       ("naut_dusk", -12.0), ("naut_dawn", -12.0)):
        jds, alts = alt_series(lambda j: (sun_geo(j - 2451543.5)["ra"],
                                         sun_geo(j - 2451543.5)["dec"]), lat, lon, jd0)
        want_rise = key in ("sunrise", "astro_dawn", "naut_dawn")
        good = []
        for k in np.where(np.diff(alts > level))[0]:
            if (alts[k + 1] > alts[k]) != want_rise:
                continue
            f = (level - alts[k]) / (alts[k + 1] - alts[k])
            good.append(from_jd(jds[k] + f * (jds[k + 1] - jds[k])))
        out[key] = min(good, key=lambda t: abs((t - from_jd(jd0)).total_seconds())) if good else None
    return out


def twilight(sun_alt: float) -> str:
    if sun_alt > 0:
        return "daylight"
    if sun_alt > -6:
        return "civil twilight"
    if sun_alt > -12:
        return "nautical twilight"
    if sun_alt > -18:
        return "astronomical twilight"
    return "full dark"


# -- The catalog: (id, name, type, RA hours, Dec deg, mag, size arcmin, note). J2000, approximate --
DSO = [
    ("M31", "Andromeda Galaxy", "galaxy", 0.71, 41.27, 3.4, "178x63", "nearest big galaxy"),
    ("M32", "M32", "galaxy", 0.71, 40.87, 8.1, "8x6", "M31 companion"),
    ("M110", "M110", "galaxy", 0.67, 41.68, 8.1, "17x10", "M31 companion"),
    ("M33", "Triangulum Galaxy", "galaxy", 1.56, 30.66, 5.7, "73x45", "face-on, needs dark sky"),
    ("M74", "M74", "galaxy", 1.61, 15.78, 9.4, "10x10", "face-on, faint"),
    ("M77", "M77", "galaxy", 2.71, -0.01, 8.9, "7x6", "bright Seyfert core"),
    ("M45", "Pleiades", "open cluster", 3.78, 24.12, 1.6, "110", "Seven Sisters, binoculars"),
    ("M1", "Crab Nebula", "supernova remnant", 5.57, 22.02, 8.4, "6x4", "1054 supernova"),
    ("M42", "Orion Nebula", "nebula", 5.59, -5.39, 4.0, "85x60", "the showpiece"),
    ("M35", "M35", "open cluster", 6.15, 24.33, 5.3, "28", ""),
    ("M37", "M37", "open cluster", 5.87, 32.55, 6.2, "24", "richest winter cluster"),
    ("M36", "M36", "open cluster", 5.60, 34.14, 6.3, "12", ""),
    ("M38", "M38", "open cluster", 5.48, 35.85, 6.4, "21", ""),
    ("M41", "M41", "open cluster", 6.77, -20.75, 4.5, "38", "below Sirius"),
    ("M50", "M50", "open cluster", 7.05, -8.33, 5.9, "16", ""),
    ("M47", "M47", "open cluster", 7.61, -14.50, 4.4, "30", ""),
    ("M46", "M46", "open cluster", 7.70, -14.82, 6.1, "27", "planetary NGC2438 inside!"),
    ("M93", "M93", "open cluster", 7.74, -23.86, 6.2, "22", ""),
    ("M44", "Beehive Cluster", "open cluster", 8.67, 19.98, 3.7, "95", "binoculars"),
    ("M67", "M67", "open cluster", 8.85, 11.80, 6.9, "30", "one of the oldest"),
    ("M48", "M48", "open cluster", 8.23, -5.80, 5.8, "54", ""),
    ("M81", "Bode's Galaxy", "galaxy", 9.93, 69.07, 6.9, "27x14", "bright spiral"),
    ("M82", "Cigar Galaxy", "galaxy", 9.93, 69.68, 8.4, "11x4", "starburst, near M81"),
    ("M65", "M65", "galaxy", 11.31, 13.09, 9.3, "10x3", "Leo Triplet"),
    ("M66", "M66", "galaxy", 11.34, 12.99, 8.9, "9x4", "Leo Triplet"),
    ("M95", "M95", "galaxy", 10.73, 11.70, 9.7, "7x5", "Leo, ringed"),
    ("M96", "M96", "galaxy", 10.78, 11.82, 9.2, "7x5", "Leo"),
    ("M105", "M105", "galaxy", 10.80, 12.58, 9.3, "5", "Leo"),
    ("M49", "M49", "galaxy", 12.49, 8.00, 8.4, "9x7", "Virgo Cluster"),
    ("M60", "M60", "galaxy", 12.51, 11.55, 8.8, "7x6", "Virgo Cluster"),
    ("M84", "M84", "galaxy", 12.42, 12.95, 9.1, "6x4", "Markarian's Chain"),
    ("M86", "M86", "galaxy", 12.44, 12.95, 8.9, "7x5", "Markarian's Chain"),
    ("M87", "M87", "galaxy", 12.52, 12.39, 8.6, "7", "giant elliptical + jet"),
    ("M100", "M100", "galaxy", 12.38, 15.82, 9.3, "7x6", "Virgo, face-on"),
    ("M104", "Sombrero Galaxy", "galaxy", 12.67, -11.62, 8.0, "9x4", "the hat"),
    ("M51", "Whirlpool Galaxy", "galaxy", 13.50, 47.20, 8.4, "11x7", "grand spiral + friend"),
    ("M63", "Sunflower Galaxy", "galaxy", 13.26, 42.03, 8.6, "12x7", ""),
    ("M94", "M94", "galaxy", 12.85, 41.12, 8.2, "11x9", "bright core, faint arms"),
    ("M64", "Black Eye Galaxy", "galaxy", 12.94, 21.68, 8.5, "9x5", "dust lane"),
    ("M106", "M106", "galaxy", 12.32, 47.30, 8.4, "18x8", ""),
    ("M101", "Pinwheel Galaxy", "galaxy", 14.05, 54.35, 7.9, "29x27", "big face-on, faint arms"),
    ("M3", "M3", "globular", 13.70, 28.38, 6.2, "18", "superb globular"),
    ("M53", "M53", "globular", 13.22, 18.17, 7.6, "13", ""),
    ("M83", "Southern Pinwheel", "galaxy", 13.62, -29.87, 7.5, "11x10", "southern spiral"),
    ("M68", "M68", "globular", 12.66, -26.74, 7.3, "12", ""),
    ("M5", "M5", "globular", 15.31, 2.08, 5.7, "23", "superb globular"),
    ("M10", "M10", "globular", 16.95, -4.10, 6.6, "20", ""),
    ("M12", "M12", "globular", 16.80, -1.95, 6.7, "16", "near M10"),
    ("M13", "Hercules Cluster", "globular", 16.70, 36.46, 5.8, "20", "best northern globular"),
    ("M92", "M92", "globular", 17.29, 43.14, 6.4, "14", ""),
    ("M4", "M4", "globular", 16.39, -26.53, 5.9, "36", "near Antares"),
    ("M80", "M80", "globular", 16.27, -22.98, 7.2, "10", ""),
    ("M62", "M62", "globular", 17.02, -30.11, 6.5, "15", ""),
    ("M19", "M19", "globular", 17.04, -26.27, 6.8, "17", "squashed (oblate)"),
    ("M11", "Wild Duck Cluster", "open cluster", 18.85, -6.27, 6.3, "14", "fan-shaped"),
    ("M26", "M26", "open cluster", 18.75, -9.38, 8.0, "15", ""),
    ("M16", "Eagle Nebula", "nebula", 18.31, -13.81, 6.4, "7", "Pillars of Creation"),
    ("M17", "Omega Nebula", "nebula", 18.35, -16.17, 6.0, "11", "the Swan"),
    ("M8", "Lagoon Nebula", "nebula", 18.06, -24.38, 6.0, "90x40", "huge, binoculars"),
    ("M20", "Trifid Nebula", "nebula", 18.04, -23.03, 6.3, "28", "three lobes"),
    ("M22", "M22", "globular", 18.61, -23.90, 5.1, "32", "huge globular"),
    ("M28", "M28", "globular", 18.41, -24.87, 7.7, "11", ""),
    ("M54", "M54", "globular", 18.92, -30.48, 7.6, "12", ""),
    ("M55", "M55", "globular", 19.67, -30.96, 6.3, "19", ""),
    ("M57", "Ring Nebula", "planetary nebula", 18.89, 33.03, 8.8, "1.4", "smoke ring"),
    ("M56", "M56", "globular", 19.28, 30.18, 8.3, "8.8", ""),
    ("M27", "Dumbbell Nebula", "planetary nebula", 19.99, 22.72, 7.5, "8x6", "apple core"),
    ("M71", "M71", "globular", 19.90, 18.78, 8.2, "7.2", "loose globular"),
    ("M29", "M29", "open cluster", 20.40, 38.53, 7.1, "7", "near Gamma Cygni"),
    ("M39", "M39", "open cluster", 21.54, 48.43, 4.6, "32", "sparse, binoculars"),
    ("M15", "M15", "globular", 21.50, 12.17, 6.2, "18", "dense core"),
    ("M2", "M2", "globular", 21.56, -0.82, 6.5, "16", ""),
    ("M30", "M30", "globular", 21.67, -23.18, 7.2, "12", ""),
    ("M52", "M52", "open cluster", 23.40, 61.60, 7.3, "13", "Bubble Nebula nearby"),
    ("M103", "M103", "open cluster", 1.56, 60.66, 7.4, "6", ""),
    ("M34", "M34", "open cluster", 2.70, 42.75, 5.5, "35", ""),
    ("M76", "Little Dumbbell", "planetary nebula", 1.70, 51.58, 10.1, "2.7x1.8", "small, high power"),
    ("M97", "Owl Nebula", "planetary nebula", 11.24, 55.02, 9.9, "3.4", "two dark eyes"),
    ("M108", "M108", "galaxy", 11.19, 55.67, 10.0, "8x2", "edge-on, near M97"),
    ("N869", "Double Cluster", "open cluster", 2.32, 57.13, 5.3, "30", "twin clusters, superb"),
    ("N457", "ET Cluster", "open cluster", 1.32, 58.29, 6.4, "13", "looks like ET"),
    ("N7000", "North America Nebula", "nebula", 20.97, 44.53, 4.0, "120x100", "huge + faint, filter helps"),
    ("N6992", "Veil Nebula (East)", "supernova remnant", 20.94, 31.72, 7.0, "60x8", "filter helps"),
    ("N7293", "Helix Nebula", "planetary nebula", 22.50, -20.84, 7.3, "25", "big + faint, low power"),
    ("N7009", "Saturn Nebula", "planetary nebula", 21.07, -11.36, 8.0, "0.4", "tiny blue football"),
    ("N253", "Sculptor Galaxy", "galaxy", 0.79, -25.29, 7.1, "27x7", "silver dollar, edge-on"),
    ("N5139", "Omega Centauri", "globular", 13.45, -47.48, 3.7, "36", "best globular in the sky"),
    ("N104", "47 Tucanae", "globular", 0.40, -72.08, 4.1, "31", "southern gem"),
    ("N6543", "Cat's Eye Nebula", "planetary nebula", 17.97, 66.63, 8.1, "0.4", "tiny blue disk"),
    ("N6946", "Fireworks Galaxy", "galaxy", 20.58, 60.15, 8.9, "11x10", "faint arms, many supernovae"),
    ("N3242", "Ghost of Jupiter", "planetary nebula", 10.41, -18.65, 7.7, "0.6", "blue disk"),
    ("N2237", "Rosette Nebula", "nebula", 6.53, 4.95, 9.0, "80x60", "very faint, filter helps"),
    ("EPSLYR", "Double Double", "multiple star", 18.75, 39.64, 4.6, "3.5", "split test in Lyra"),
    ("ALBIREO", "Albireo", "double star", 19.51, 27.96, 3.1, "0.6", "gold + blue, superb"),
    ("CR399", "Coathanger", "asterism", 19.42, 20.18, 3.6, "60", "binocular asterism"),
]

STARS = [  # the bright ones, for getting your bearings
    ("Sirius", 6.75, -16.72, -1.5, ""),
    ("Canopus", 6.40, -52.70, -0.7, ""),
    ("Arcturus", 14.26, 19.18, -0.1, ""),
    ("Vega", 18.62, 38.78, 0.0, ""),
    ("Capella", 5.28, 46.00, 0.1, ""),
    ("Rigel", 5.24, -8.20, 0.1, ""),
    ("Procyon", 7.66, 5.22, 0.3, ""),
    ("Betelgeuse", 5.92, 7.41, 0.4, "variable, red"),
    ("Achernar", 1.63, -57.24, 0.5, ""),
    ("Altair", 19.85, 8.87, 0.8, ""),
    ("Aldebaran", 4.60, 16.51, 0.9, "variable, orange"),
    ("Antares", 16.49, -26.43, 0.9, "variable, red"),
    ("Spica", 13.42, -11.16, 1.0, ""),
    ("Pollux", 7.76, 28.03, 1.1, ""),
    ("Fomalhaut", 22.96, -29.62, 1.2, ""),
    ("Deneb", 20.69, 45.28, 1.3, ""),
    ("Mimosa", 12.79, -59.69, 1.3, "Southern Cross"),
    ("Regulus", 10.14, 11.97, 1.4, ""),
    ("Castor", 7.58, 31.89, 1.6, "actually 6 stars!"),
    ("Gacrux", 12.52, -57.11, 1.6, "Southern Cross, red"),
    ("Dubhe", 11.06, 61.75, 1.8, "Big Dipper pointer"),
    ("Alkaid", 13.79, 49.31, 1.9, "Big Dipper handle"),
    ("Polaris", 2.53, 89.26, 2.0, "the North Star"),
    ("Mizar", 13.40, 54.93, 2.0, "split with Alcor"),
    ("Algol", 3.14, 40.96, 2.1, "variable, winks"),
]

PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]


# -- The sky model: everything, where it is, right now ------------------------------------------------
def mag_dot(mag: float) -> float:
    """Magnitude -> chart dot radius in px. Brighter is bigger, always 1.5..7."""
    return max(1.5, min(7.0, 8.0 - mag))


def compute_frame(moment: dt.datetime, lat: float, lon: float) -> dict:
    """Every object with alt/az for a local time + site. The GUI calls this every frame."""
    jd, d = to_jd(moment), to_jd(moment) - 2451543.5
    earth = earth_helio(d)
    sun, moon = sun_geo(d), moon_geo(d, sun_geo(d))
    illum, phase = moon_phase(jd)
    sun_alt, sun_az = altaz(sun["ra"], sun["dec"], lat, lon, jd)
    moon_alt, moon_az = altaz(moon["ra"], moon["dec"], lat, lon, jd)
    objects = [
        {"id": "SUN", "name": "Sun", "kind": "sun", "dtype": "star", "ra": sun["ra"],
         "dec": sun["dec"], "mag": -26.7, "size": "32'", "note": "DO NOT point optics at it",
         "alt": sun_alt, "az": sun_az, "extra": {}},
        {"id": "MOON", "name": "Moon", "kind": "moon", "dtype": "moon", "ra": moon["ra"],
         "dec": moon["dec"], "mag": max(-12.7, -12.7 - 2.5 * math.log10(max(illum, 0.001))),
         "size": "31'", "note": f"{phase}, {illum * 100:.0f}% lit",
         "alt": moon_alt, "az": moon_az, "extra": {"illum": illum, "phase": phase}},
    ]
    for name in PLANETS:
        g = planet_geo(name, d, earth)
        alt, az = altaz(g["ra"], g["dec"], lat, lon, jd)
        objects.append({"id": name.upper(), "name": name, "kind": "planet", "dtype": "planet",
                        "ra": g["ra"], "dec": g["dec"], "mag": g["mag"], "size": "",
                        "note": f"{g['delta']:.2f} AU from Earth", "alt": alt, "az": az,
                        "extra": {"delta": g["delta"]}})
    for oid, name, dtype, ra, dec, mag, size, note in DSO:
        ra, dec = precess(ra, dec, 2451545.0, jd)  # catalog is J2000; the sky is tonight
        alt, az = altaz(ra, dec, lat, lon, jd)
        objects.append({"id": oid, "name": f"{oid} {name}" if not name.startswith(oid) else name,
                        "kind": "dso", "dtype": dtype, "ra": ra, "dec": dec, "mag": mag,
                        "size": size, "note": note, "alt": alt, "az": az, "extra": {}})
    for name, ra, dec, mag, note in STARS:
        ra, dec = precess(ra, dec, 2451545.0, jd)
        alt, az = altaz(ra, dec, lat, lon, jd)
        objects.append({"id": "S:" + name, "name": name, "kind": "star", "dtype": "star",
                        "ra": ra, "dec": dec, "mag": mag, "size": "", "note": note,
                        "alt": alt, "az": az, "extra": {}})
    up_now = sorted([o for o in objects if o["alt"] > 0 and o["kind"] != "star"],
                    key=lambda o: -o["alt"])
    return {"jd": jd, "moment": moment, "sun_alt": sun_alt, "twilight": twilight(sun_alt),
            "moon": objects[1], "objects": objects, "up_now": up_now}


# -- Self-test --------------------------------------------------------------------------------------
def selftest() -> int:
    utc = dt.timezone.utc
    bad = 0

    def check(ok, what):
        nonlocal bad
        print(("PASS " if ok else "FAIL ") + what)
        bad += (not ok)

    check(abs(to_jd(dt.datetime(2000, 1, 1, 12, tzinfo=utc)) - 2451545.0) < 1e-6,
          "JD of 2000-01-01 12:00 UTC is 2451545.0")
    check(abs(gmst_deg(2451545.0) - 280.46061837) < 1e-6, "GMST at J2000 is 280.4606 deg")
    jun = sun_geo(to_jd(dt.datetime(2026, 6, 21, 12, tzinfo=utc)) - 2451543.5)["dec"]
    check(abs(jun - 23.44) < 0.15, f"June solstice Sun dec {jun:.2f} ~= +23.44")
    dec = sun_geo(to_jd(dt.datetime(2026, 12, 21, 12, tzinfo=utc)) - 2451543.5)["dec"]
    check(abs(dec + 23.44) < 0.15, f"December solstice Sun dec {dec:.2f} ~= -23.44")
    equ = sun_geo(to_jd(dt.datetime(2026, 3, 20, 12, tzinfo=utc)) - 2451543.5)["dec"]
    check(abs(equ) < 0.4, f"March equinox Sun dec {equ:.2f} ~= 0")
    p1 = altaz(2.53, 89.26, 40.0, -86.0, to_jd(dt.datetime(2026, 11, 10, 12, tzinfo=utc)))[0]
    p2 = altaz(2.53, 89.26, 40.0, -86.0, to_jd(dt.datetime(2026, 11, 10, 18, tzinfo=utc)))[0]
    check(abs(p1 - 40) < 0.8 and abs(p2 - 40) < 0.8,
          f"Polaris sits at the latitude ({p1:.1f}/{p2:.1f} at lat 40)")
    jd0 = to_jd(dt.datetime(2026, 11, 10, 12, tzinfo=utc))
    lst = rev(gmst_deg(jd0) - 86.0) / 15.0
    check(abs(altaz(lst, 40.0, 40.0, -86.0, jd0)[0] - 90) < 0.05, "dec=lat on the meridian is zenith")
    check(moon_phase(to_jd(dt.datetime(2000, 1, 6, 18, tzinfo=utc)))[0] < 0.06,
          "new Moon 2000-01-06 is dark")
    check(moon_phase(to_jd(dt.datetime(2000, 1, 21, 5, tzinfo=utc)))[0] > 0.94,
          "full Moon 2000-01-21 is lit")
    maxv = maxm = 0.0
    earth = None
    for w in range(0, 730, 7):
        d = to_jd(dt.datetime(2025, 1, 1, tzinfo=utc)) + w - 2451543.5
        earth = earth_helio(d)
        sun = sun_geo(d)
        for name in ("Venus", "Mercury"):
            g = planet_geo(name, d, earth)
            sep = separation(sun["ra"], sun["dec"], g["ra"], g["dec"])
            maxv = max(maxv, sep) if name == "Venus" else maxv
            maxm = max(maxm, sep) if name == "Mercury" else maxm
    check(maxv < 48.5, f"Venus never strays past 48.5 deg from the Sun (max {maxv:.1f})")
    check(maxm < 29.0, f"Mercury never strays past 29 deg from the Sun (max {maxm:.1f})")
    er = [helio("Earth", to_jd(dt.datetime(2026, m, 15, tzinfo=utc)) - 2451543.5)["r"]
          for m in range(1, 13)]
    check(min(er) > 0.98 and max(er) < 1.02, f"Earth orbits at ~1 AU ({min(er):.3f}..{max(er):.3f})")
    mr = [planet_geo("Mars", to_jd(dt.datetime(2026, m, 15, tzinfo=utc)) - 2451543.5,
                     earth_helio(to_jd(dt.datetime(2026, m, 15, tzinfo=utc)) - 2451543.5))["r"]
          for m in range(1, 13)]
    check(min(mr) > 1.38 and max(mr) < 1.68, f"Mars orbits at ~1.52 AU ({min(mr):.2f}..{max(mr):.2f})")
    ok = True
    for y in (2000, 2010, 2020, 2026, 2030):
        d = to_jd(dt.datetime(y, 1, 1, tzinfo=utc)) - 2451543.5
        e = earth_helio(d)
        for name in PLANETS:
            g = planet_geo(name, d, e)
            ok = ok and all(math.isfinite(v) for v in (g["ra"], g["dec"], g["mag"]))
    check(ok, "all 7 planets finite RA/Dec/mag on 5 dates, 2000-2030")
    ids = [r[0] for r in DSO]
    check(len(set(ids)) == len(ids) and len(DSO) >= 80, f"catalog: {len(DSO)} DSO, ids unique")
    check(len(STARS) == 25, f"catalog: {len(STARS)} stars")
    check(all(0 <= r[3] < 24 and -90 <= r[4] <= 90 and -2 <= r[5] <= 11 for r in DSO),
          "catalog: every DSO has sane RA/Dec/mag")
    m31 = next(r for r in DSO if r[0] == "M31")
    check(abs(m31[3] - 0.71) < 0.05, "spot check: M31 RA ~= 0.71h")
    vega = next(s for s in STARS if s[0] == "Vega")
    pv = precess(vega[1], vega[2], 2451545.0, to_jd(dt.datetime(2026, 11, 10, tzinfo=utc)))
    dv = rev((pv[0] - vega[1]) * 15.0)
    check(0.15 < dv < 0.35, f"Vega precesses +{dv:.2f} deg RA, J2000 to Nov 2026")
    rt = precess(pv[0], pv[1], to_jd(dt.datetime(2026, 11, 10, tzinfo=utc)), 2451545.0)
    check(abs(rt[0] - vega[1]) * 15 < 1e-3 and abs(rt[1] - vega[2]) < 1e-3,
          "precession round-trips to 1e-3 deg")
    check(all(compass(a) == c for a, c in
              ((0, "N"), (45, "NE"), (90, "E"), (135, "SE"), (180, "S"), (225, "SW"),
               (270, "W"), (315, "NW"))), "compass points N/NE/E/SE/S/SW/W/NW")
    ev = events((5.59, -5.39), 40.0, -86.0, to_jd(dt.datetime(2026, 11, 10, 12, tzinfo=utc)))
    good = ev["flag"] == "ok" and ev["rise"] < ev["transit"] < ev["set"]
    talt = altaz(5.59, -5.39, 40.0, -86.0, to_jd(ev["transit"]))[0] if good else -99
    check(good and abs(talt - (90 - abs(40 - -5.39))) < 1.0,
          f"M42 rises, transits {talt:.1f} deg, sets, in that order")
    check(events((0.40, -72.08), 40.0, -86.0, jd0)["flag"] == "never-rises",
          "47 Tuc never rises at 40N")
    check(events((2.53, 89.26), 40.0, -86.0, jd0)["flag"] == "up-all-day",
          "Polaris never sets at 40N")
    se = sun_events(40.0, -86.0, to_jd(dt.datetime(2026, 11, 11, 5, tzinfo=utc)))
    check(all(se[k] for k in ("sunset", "astro_dusk", "astro_dawn", "sunrise"))
          and se["sunset"] < se["astro_dusk"] < se["astro_dawn"] < se["sunrise"],
          "sunset < astro dusk < astro dawn < sunrise")
    md = [moon_geo(to_jd(dt.datetime(2026, 11, 1, tzinfo=utc)) + n - 2451543.5,
                   sun_geo(to_jd(dt.datetime(2026, 11, 1, tzinfo=utc)) + n - 2451543.5))["r"]
          for n in range(30)]
    check(min(md) > 56 and max(md) < 64, f"Moon orbits at ~60 earth radii ({min(md):.1f}..{max(md):.1f})")
    r1 = sun_geo(to_jd(dt.datetime(2026, 10, 11, 12, tzinfo=utc)) - 2451543.5)["ra"] * 15
    r2 = sun_geo(to_jd(dt.datetime(2026, 11, 10, 12, tzinfo=utc)) - 2451543.5)["ra"] * 15
    check(abs(rev(r2 - r1) - 30) < 3, "Sun moves ~1 deg/day along the ecliptic")
    now = dt.datetime(2026, 11, 10, 12, tzinfo=dt.timezone(dt.timedelta(hours=-5)))
    check(parse_when("21:30", now) == now.replace(hour=21, minute=30, second=0, microsecond=0)
          and parse_when("2026-11-14 21:00", now) == dt.datetime(2026, 11, 14, 21, tzinfo=now.tzinfo),
          "--at parses 'HH:MM' and 'YYYY-MM-DD HH:MM'")
    check([mag_dot(m) for m in (1, 3, 5)] == sorted((mag_dot(1), mag_dot(3), mag_dot(5)),
                                                    reverse=True)
          and all(1.5 <= mag_dot(m) <= 7 for m in range(-2, 13)),
          "chart dots shrink with magnitude, clamped 1.5..7px")
    print("ALL PASSED" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


# -- The window -----------------------------------------------------------------------------------
_RED = False  # night-vision mode: everything through a red filter


def C(rgb: tuple) -> tuple:
    if not _RED:
        return rgb
    return (min(255, int(0.30 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2])), 0, 0)


PLANET_COLORS = {"Mercury": (170, 160, 150), "Venus": (255, 245, 220), "Mars": (255, 120, 80),
                 "Jupiter": (235, 205, 165), "Saturn": (230, 210, 150), "Uranus": (150, 220, 220),
                 "Neptune": (120, 150, 255)}


def fmt_ra(ra: float) -> str:
    h, m = int(ra), int((ra * 60) % 60)
    return f"{h:02d}:{m:02d}"


def fmt_dec(dec: float) -> str:
    s = "+" if dec >= 0 else "-"
    return f"{s}{abs(int(dec)):02d}:{int((abs(dec) * 60) % 60):02d}"


def fmt_hm(moment) -> str:
    return moment.strftime("%H:%M") if moment else "--:--"


def main() -> int:
    ap = argparse.ArgumentParser(description="Backyard-telescope sky guide: what's up tonight")
    ap.add_argument("--lat", type=float, default=40.0, help="site latitude, default 40.0")
    ap.add_argument("--lon", type=float, default=-86.0, help="site longitude East+, default -86.0")
    ap.add_argument("--at", default=None, help='start time, "YYYY-MM-DD HH:MM" or "HH:MM" local')
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180):
        print("site out of range: --lat -90..90, --lon -180..180")
        return 2

    import pygame  # only needed for the window, so the self-test runs without it

    global _RED
    W, H = 1000, 660
    CX, CY, R = 325, 345, 295
    PX = 655  # right panel starts here

    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Bordeom - sky")
    canvas = pygame.Surface((W, H))
    f_big, f_med, f_small, f_tiny = (pygame.font.Font(None, s) for s in (28, 21, 18, 15))
    clock = pygame.time.Clock()

    def txt(font, text, pos, color=(220, 225, 235)):
        canvas.blit(font.render(str(text), False, C(color)), pos)

    local = dt.datetime.now().astimezone().tzinfo
    sim = parse_when(args.at, dt.datetime.now(local)) if args.at else dt.datetime.now(local)
    paused, help_on = False, True
    sel_id, positions = "MOON", {}
    sun_cache, ev_cache = {}, {}

    def sunline(frame):
        key = (args.lat, args.lon, sim.date())
        if key not in sun_cache:
            sun_cache.clear()
            sun_cache[key] = sun_events(args.lat, args.lon, frame["jd"])
        se = sun_cache[key]
        return (f"sunset {fmt_hm(se['sunset'].astimezone(local))} - "
                f"astro dark {fmt_hm(se['astro_dusk'].astimezone(local)) if se['astro_dusk'] else '--:--'}"
                f"-{fmt_hm(se['astro_dawn'].astimezone(local)) if se['astro_dawn'] else '--:--'} - "
                f"sunrise {fmt_hm(se['sunrise'].astimezone(local))}")

    def selection(frame):
        nonlocal sel_id
        objs = {o["id"]: o for o in frame["objects"]}
        if sel_id not in objs:
            sel_id = "MOON"
        return objs[sel_id]

    def selection_events(obj, frame):
        key = (obj["id"], sim.date(), sim.hour)
        if key not in ev_cache:
            ev_cache.clear()
            if obj["kind"] == "sun":
                radec = lambda j: (sun_geo(j - 2451543.5)["ra"], sun_geo(j - 2451543.5)["dec"])
                ev_cache[key] = events(radec, args.lat, args.lon, frame["jd"], horizon=-0.833)
            elif obj["kind"] in ("moon", "planet"):
                d0 = frame["jd"] - 2451543.5
                earth = earth_helio(d0)
                base = moon_geo(d0, sun_geo(d0)) if obj["kind"] == "moon" else planet_geo(
                    obj["name"], d0, earth)
                ev_cache[key] = events((base["ra"], base["dec"]), args.lat, args.lon, frame["jd"])
            else:
                ev_cache[key] = events((obj["ra"], obj["dec"]), args.lat, args.lon, frame["jd"])
        return ev_cache[key]

    def chart_xy(alt, az):
        r = R * (90 - alt) / 90.0
        return CX + r * math.sin(az * D2R), CY - r * math.cos(az * D2R)

    running = True
    while running:
        wall = clock.tick(30) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos[0] * W / screen.get_width(), ev.pos[1] * H / screen.get_height()
                best, bestd = None, 16.0
                for oid, (x, y) in positions.items():
                    dd = math.hypot(mx - x, my - y)
                    if dd < bestd:
                        best, bestd = oid, dd
                if best:
                    sel_id = best
            elif ev.type == pygame.KEYDOWN:
                k, mods = ev.key, pygame.key.get_mods()
                fine = bool(mods & (pygame.KMOD_SHIFT | pygame.KMOD_CTRL))
                if k in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif k == pygame.K_LEFT:
                    sim -= dt.timedelta(minutes=10 if fine else 60)
                elif k == pygame.K_RIGHT:
                    sim += dt.timedelta(minutes=10 if fine else 60)
                elif k == pygame.K_UP:
                    sim -= dt.timedelta(hours=1 if fine else 24)
                elif k == pygame.K_DOWN:
                    sim += dt.timedelta(hours=1 if fine else 24)
                elif k in (pygame.K_HOME, pygame.K_0):
                    sim = dt.datetime.now(local)
                elif k == pygame.K_TAB:
                    up = frame["up_now"]
                    if up:
                        ids = [o["id"] for o in up]
                        i = ids.index(sel_id) if sel_id in ids else (-1 if mods & pygame.KMOD_SHIFT
                                                                     else 0)
                        sel_id = ids[(i + (-1 if mods & pygame.KMOD_SHIFT else 1)) % len(ids)]
                elif k == pygame.K_r:
                    _RED = not _RED
                elif k == pygame.K_SPACE:
                    paused = not paused
                elif k in (pygame.K_f, pygame.K_RETURN):
                    try:
                        pygame.display.toggle_fullscreen()
                    except pygame.error:
                        pass
                elif k == pygame.K_h:
                    help_on = not help_on
                elif k == pygame.K_s:
                    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
                    path = os.path.join(HERE, "shots", time.strftime("sky-%Y%m%d-%H%M%S.png"))
                    pygame.image.save(canvas, path)

        if not paused:
            sim += dt.timedelta(seconds=wall)
        frame = compute_frame(sim, args.lat, args.lon)
        sel = selection(frame)

        canvas.fill(C((8, 10, 18)))
        pygame.draw.circle(canvas, C((10, 14, 30)), (CX, CY), R)  # the sky
        for ring, lab in ((R / 3, "60"), (2 * R / 3, "30")):
            pygame.draw.circle(canvas, C((35, 45, 75)), (CX, CY), int(ring), 1)
            txt(f_tiny, lab, (CX + 4, CY - ring - 8), (90, 100, 140))
        pygame.draw.circle(canvas, C((110, 130, 190)), (CX, CY), R, 2)  # horizon
        for name, a in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            txt(f_med, name, (CX + (R + 12) * math.sin(a * D2R) - 6,
                              CY - (R + 12) * math.cos(a * D2R) - 9), (150, 165, 210))
        txt(f_tiny, "Z", (CX - 3, CY - 7), (90, 100, 140))

        positions = {}
        for o in frame["objects"]:
            if o["alt"] <= 0:
                continue
            x, y = chart_xy(o["alt"], o["az"])
            positions[o["id"]] = (x, y)
            r = mag_dot(o["mag"])
            if o["kind"] == "star":
                pygame.draw.circle(canvas, C((255, 255, 255)), (x, y), max(1, int(r * 0.8)))
            elif o["kind"] == "dso":
                pygame.draw.circle(canvas, C((140, 200, 255)), (x, y), 5, 1)
                pygame.draw.circle(canvas, C((140, 200, 255)), (x, y), 1)
            elif o["kind"] == "planet":
                pygame.draw.circle(canvas, C(PLANET_COLORS[o["name"]]), (x, y), int(r))
                if o["name"] == "Saturn":
                    pygame.draw.ellipse(canvas, C((230, 210, 150)),
                                        (x - r - 3, y - 2, 2 * (r + 3), 5), 1)
            elif o["kind"] == "moon":
                pygame.draw.circle(canvas, C((60, 62, 75)), (x, y), 10)
                illum = o["extra"]["illum"]
                pygame.draw.circle(canvas, C((235, 235, 240)), (x, y), 10, 1)
                lx = x + (10 - 20 * illum) * (1 if "Wax" in o["extra"]["phase"] or
                                              o["extra"]["phase"] == "Full" else -1)
                pygame.draw.circle(canvas, C((235, 235, 240)), (lx, y), int(10 * illum))
            elif o["kind"] == "sun":
                pygame.draw.circle(canvas, C((255, 210, 90)), (x, y), 10)
                for a in range(0, 360, 45):
                    x2, y2 = x + 15 * math.sin(a * D2R), y - 15 * math.cos(a * D2R)
                    pygame.draw.line(canvas, C((255, 210, 90)), (x, y), (x2, y2), 1)
        if sel["id"] in positions:
            x, y = positions[sel["id"]]
            pygame.draw.circle(canvas, C((255, 90, 90)), (x, y), 13, 1)
            pygame.draw.line(canvas, C((255, 90, 90)), (x - 18, y), (x - 13, y), 1)
            pygame.draw.line(canvas, C((255, 90, 90)), (x + 13, y), (x + 18, y), 1)
            pygame.draw.line(canvas, C((255, 90, 90)), (x, y - 18), (x, y - 13), 1)
            pygame.draw.line(canvas, C((255, 90, 90)), (x, y + 13), (x, y + 18), 1)
        for o in frame["objects"]:
            if o["id"] not in positions:
                continue
            if not (o["id"] == sel["id"] or o["kind"] in ("planet", "moon", "sun")
                    or (o["kind"] == "dso" and o["mag"] <= 5)
                    or (o["kind"] == "star" and o["mag"] <= 1.0)):
                continue
            x, y = positions[o["id"]]
            label = o["name"] if len(o["name"]) <= 16 else o["id"]
            txt(f_tiny, label, (x + 8, y - 6),
                (255, 210, 120) if o["id"] == sel["id"] else (170, 180, 205))

        # right panel: time + site, up-now list, selection detail
        txt(f_big, "WHAT'S UP TONIGHT", (PX, 8), (255, 210, 120))
        off = (sim - dt.datetime.now(local)).total_seconds()
        when = sim.strftime("%a %b %d  %H:%M") + ("  (held)" if paused else "")
        if abs(off) > 90:
            when += f"  ({'+' if off > 0 else '-'}{abs(int(off)) // 86400}d{abs(int(off)) % 86400 // 3600}h)"
        txt(f_med, when, (PX, 40))
        txt(f_small, f"site {abs(args.lat):.1f}{'N' if args.lat >= 0 else 'S'} "
                     f"{abs(args.lon):.1f}{'E' if args.lon >= 0 else 'W'}  -  {frame['twilight']}",
            (PX, 64), (170, 180, 205))
        txt(f_small, sunline(frame), (PX, 84), (170, 180, 205))
        up = frame["up_now"]
        txt(f_med, f"UP NOW ({len(up)})", (PX, 110), (255, 210, 120))
        y = 134
        for o in up[:13]:
            col = (255, 210, 120) if o["id"] == sel["id"] else (220, 225, 235)
            if o["id"] == sel["id"]:
                pygame.draw.rect(canvas, C((40, 36, 28)), (PX - 4, y - 2, W - PX - 6, 20))
            txt(f_small, f"{o['name'][:20]:20s} {o['alt']:4.0f} {compass(o['az']):3s} {o['mag']:5.1f}",
                (PX, y), col)
            y += 20
        y += 6
        txt(f_med, "PICK", (PX, y), (255, 210, 120))
        y += 24
        ms = separation(frame["moon"]["ra"], frame["moon"]["dec"], sel["ra"], sel["dec"])
        detail = [f"{sel['name']}", f"{sel['dtype']}  mag {sel['mag']:.1f}"
                  + (f"  {sel['size']}" if sel["size"] else ""),
                  f"RA {fmt_ra(sel['ra'])}  Dec {fmt_dec(sel['dec'])}"]
        if sel["alt"] > 0:
            detail.append(f"{sel['alt']:.0f} deg up, {compass(sel['az'])} (az {sel['az']:.0f})")
        else:
            detail.append(f"{-sel['alt']:.0f} deg UNDER the horizon")
        sev = selection_events(sel, frame)
        if sev["flag"] == "ok":
            detail.append(f"rises {fmt_hm(sev['rise'].astimezone(local))} - "
                          f"transits {fmt_hm(sev['transit'].astimezone(local))} - "
                          f"sets {fmt_hm(sev['set'].astimezone(local))}")
        elif sev["flag"] == "up-all-day":
            detail.append(f"up all day - transits {fmt_hm(sev['transit'].astimezone(local))}")
        else:
            detail.append("never rises at this site")
        if sel["id"] != "MOON":
            detail.append(f"Moon {ms:.0f} deg away ({frame['moon']['extra']['phase'].lower()})")
        if sel["note"]:
            detail.append(sel["note"][:46])
        for line in detail[:7]:
            txt(f_small, line, (PX, y))
            y += 19

        if frame["sun_alt"] > -0.5:
            txt(f_med, "SUN IS UP - never point optics at the Sun", (24, 8), (255, 90, 90))
        if help_on:
            for n, line in enumerate(("arrows: time (shift=fine)  Tab: pick  click: pick  R: red mode",
                                      "Space: hold time  F: fullscreen  S: shot  H: help  Q: quit")):
                txt(f_small, line, (24, H - 44 + n * 19), (150, 165, 210))
        screen.blit(canvas, (0, 0))
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
