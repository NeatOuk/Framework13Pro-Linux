"""Weather for the bar (custom/weather, fw-weather) from Open-Meteo (no key, stdlib urllib only).

Store: `weather_city` (as typed in Settings → System; empty = the time zone's city), `weather_place` (geocoded once: name, label, lat, lon,
query = the city it was resolved from), `weather_units` ("c" / "f"). Forecast cached in ~/.cache/fw13/weather.json
for 30 minutes; offline or on an error the bar shows the last cached value, dimmed (class "stale").
"""
import datetime
import html
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

from . import store

SIGNAL = 15
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "fw13", "weather.json")
MAX_AGE = 1800
GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
# WMO weather code → (Font Awesome 6 Free icon, words); the night icon replaces the sun when it's dark
SUN, MOON, CLOUD_SUN, CLOUD_MOON = "", "", "", ""
CODES = [((0,), SUN, "Clear"), ((1, 2), CLOUD_SUN, "Partly cloudy"), ((3,), "", "Overcast"),
         ((45, 48), "", "Fog"), (range(51, 58), "", "Drizzle"), (range(61, 68), "", "Rain"),
         (range(71, 78), "", "Snow"), ((80, 81, 82), "", "Showers"), ((85, 86), "", "Snow showers"),
         (range(95, 100), "", "Thunderstorm")]


def describe(code, day=True):
    for codes, icon, words in CODES:
        if code in codes:
            if not day:
                icon = {SUN: MOON, CLOUD_SUN: CLOUD_MOON}.get(icon, icon)
            return icon, words
    return "", "Unknown"


def _get(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "fw13-weather"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def geocode(city):
    """'Phnom Penh' or 'Paris, US' → {name, label, lat, lon, query}; None if not found. Raises on network errors."""
    name, _, hint = (p.strip() for p in city.partition(","))
    res = _get(GEO, {"name": name, "count": 10, "language": "en", "format": "json"}).get("results") or []
    if hint:  # Open-Meteo matches the name only: pick the result whose country/region/country code fits
        h = hint.lower()
        res = [r for r in res if any(str(r.get(k, "")).lower().startswith(h)
                                     for k in ("country", "admin1", "country_code"))] or res
    if not res:
        return None
    r = res[0]
    label = ", ".join(x for x in (r["name"], r.get("country")) if x)
    return {"name": r["name"], "label": label, "lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "query": city}


def forecast(place, units):
    d = _get(FORECAST, {"latitude": place["lat"], "longitude": place["lon"], "timezone": "auto", "forecast_days": 3,
                        "current": "temperature_2m,weather_code,is_day",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
                        "temperature_unit": "fahrenheit" if units == "f" else "celsius"})
    c, dl = d["current"], d["daily"]
    tz = datetime.timezone(datetime.timedelta(seconds=d.get("utc_offset_seconds", 0)))  # times are the place's

    def epoch(t):
        return int(datetime.datetime.fromisoformat(t).replace(tzinfo=tz).timestamp())
    return {"sun": [[t, epoch(r), epoch(s)] for t, r, s in zip(dl["time"], dl["sunrise"], dl["sunset"])],
            "temp": round(c["temperature_2m"]), "code": int(c["weather_code"]), "day": bool(c.get("is_day", 1)),
            "days": [{"date": t, "code": int(w), "max": round(hi), "min": round(lo)} for t, w, hi, lo in
                     zip(dl["time"], dl["weather_code"], dl["temperature_2m_max"], dl["temperature_2m_min"])]}


def tz_city():
    """The city of the system time zone (/etc/localtime → Asia/Phnom_Penh → "Phnom Penh"); "" for Etc/UTC or none."""
    zone = os.path.realpath("/etc/localtime").partition("/zoneinfo/")[2]
    region, _, name = zone.rpartition("/")
    return "" if not region or region.startswith("Etc") else name.replace("_", " ")


def city():
    """The city typed in Settings, else the time zone's city."""
    return (store.get("weather_city") or "").strip() or tz_city()


def place():
    """The stored place for city(), geocoding again when the city changed; None without a city."""
    name = city()
    if not name:
        return None
    p = store.get("weather_place")
    if not (isinstance(p, dict) and p.get("query") == name):
        p = geocode(name)
        store.set("weather_place", p)
    return p


def _read_cache():
    try:
        return json.load(open(CACHE))
    except (OSError, ValueError):
        return {}


def _write_cache(data):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, CACHE)


def cached():
    """(cache, stale): the forecast cache, fetched again when older than MAX_AGE, the place or units changed, or it
    predates sunrise/sunset; stale = offline or an error, so the last cache. cache is None when the city isn't found."""
    units = "f" if store.get("weather_units") == "f" else "c"
    cache = _read_cache()
    try:
        p = place()
        if p is None:
            return None, False
        key = f"{p['lat']},{p['lon']},{units}"
        if (cache.get("key") != key or time.time() - cache.get("time", 0) > MAX_AGE
                or "sun" not in cache.get("data", {})):
            cache = {"key": key, "time": time.time(), "label": p["label"], "units": units, "data": forecast(p, units)}
            _write_cache(cache)
    except (OSError, ValueError, KeyError, TypeError):  # offline, HTTP error or an unexpected answer: last value
        return cache, True
    return cache, False


def sun_today():
    """(sunset, sunrise) of today as epoch seconds from the forecast; None without a city or data (offline)."""
    if not city():
        return None
    cache, _ = cached()
    today = datetime.date.today().isoformat()
    for day, rise, sset in ((cache or {}).get("data") or {}).get("sun", []):
        if day == today:
            return sset, rise
    return None


def bar():
    """Waybar JSON: icon + temperature; {"text": ""} (hidden) without a city."""
    if not city():
        return {"text": ""}
    cache, stale = cached()
    if cache is None:
        return {"text": " ?", "class": "stale", "tooltip": "City not found: check Settings → System → Weather"}
    w = cache.get("data")
    if not w:
        return {"text": "", "tooltip": "Weather: no data yet (offline?)"}
    icon, words = describe(w["code"], w["day"])
    deg = "°F" if cache.get("units") == "f" else "°C"
    lines = [cache.get("label", ""), f"Now {w['temp']}{deg} · {words}", ""]
    for d in w["days"]:
        day = datetime.date.fromisoformat(d["date"]).strftime("%a")
        lines.append(f"{day}  {d['max']}° / {d['min']}°  {describe(d['code'])[1]}")
    if stale:
        lines.append(f"\nOffline · from {time.strftime('%H:%M', time.localtime(cache.get('time', 0)))}")
    tip = html.escape("\n".join(lines), quote=False)  # waybar reads Pango markup
    return {"text": f"{icon} {w['temp']}°", "class": "stale" if stale else "ok", "tooltip": tip}


def refresh_bar():
    subprocess.run(["pkill", f"-RTMIN+{SIGNAL}", "-x", "waybar"], stderr=subprocess.DEVNULL)
