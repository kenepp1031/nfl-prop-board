"""Game-day weather for outdoor games, from Open-Meteo.

Free, no key, no account, no quota a board like this could reach. One
request covers every outdoor venue on the slate: the API takes a list of
coordinates and answers with one forecast per venue.

What comes back per game is the weather over the game WINDOW -- kickoff to
about three hours after -- not the weather at kickoff. A front that arrives
in the third quarter is still the game's weather.

    weather.forecasts(2026, 3)   ->  {game_id: {...} or None}

What the model does with it lives in model.py (weather_factors); what the
header says about it is describe() below.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request

import common
import nflverse

# Forecasts are re-issued hourly; three hours is fresh enough for a game
# that is days away and cheap enough for one that is this afternoon.
FORECAST_HOURS = 3
# How far out Open-Meteo will forecast. Next week's games are inside it.
FORECAST_DAYS = 16
# Past about a week a forecast is climatology with a haircut. Beyond this
# the board shows the number but does not price on it.
HORIZON_DAYS = 7
# Hours of game the forecast is averaged over, the kickoff hour included.
GAME_HOURS = 4

API = "https://api.open-meteo.com/v1/forecast"
FIELDS = ("temperature_2m", "apparent_temperature", "precipitation_probability",
          "precipitation", "snowfall", "weather_code",
          "wind_speed_10m", "wind_gusts_10m")

# nflverse stadium_id -> (lat, lon, what the roof is when games.csv leaves it
# blank). The file fills `roof` in ahead of time for fixed venues and leaves
# it empty for retractables and one-off sites. A retractable roof is assumed
# CLOSED when nobody has said: that is what the operators do whenever the
# weather is worth caring about, so pricing it as indoors is right on every
# day the difference would matter.
VENUES = {
    "ATL97": (33.7554, -84.4010, "retractable"),    # Mercedes-Benz Stadium
    "BAL00": (39.2780, -76.6227, "outdoors"),       # M&T Bank Stadium
    "BOS00": (42.0909, -71.2643, "outdoors"),       # Gillette Stadium
    "BUF00": (42.7738, -78.7870, "outdoors"),       # Highmark Stadium
    "CAR00": (35.2258, -80.8528, "outdoors"),       # Bank of America Stadium
    "CHI98": (41.8623, -87.6167, "outdoors"),       # Soldier Field
    "CIN00": (39.0954, -84.5160, "outdoors"),       # Paycor Stadium
    "CLE00": (41.5061, -81.6995, "outdoors"),       # Huntington Bank Field
    "DAL00": (32.7473, -97.0945, "retractable"),    # AT&T Stadium
    "DEN00": (39.7439, -105.0201, "outdoors"),      # Empower Field at Mile High
    "DET00": (42.3400, -83.0456, "dome"),           # Ford Field
    "GNB00": (44.5013, -88.0622, "outdoors"),       # Lambeau Field
    "HOU00": (29.6847, -95.4107, "retractable"),    # NRG Stadium
    "IND00": (39.7601, -86.1639, "retractable"),    # Lucas Oil Stadium
    "JAX00": (30.3239, -81.6373, "outdoors"),       # EverBank Stadium
    "KAN00": (39.0489, -94.4839, "outdoors"),       # Arrowhead
    "LAX01": (33.9535, -118.3392, "dome"),          # SoFi Stadium
    "MIA00": (25.9580, -80.2389, "outdoors"),       # Hard Rock Stadium
    "MIN01": (44.9736, -93.2575, "dome"),           # U.S. Bank Stadium
    "NAS00": (36.1665, -86.7713, "outdoors"),       # Nissan Stadium
    "NOR00": (29.9511, -90.0812, "dome"),           # Caesars Superdome
    "NYC01": (40.8135, -74.0745, "outdoors"),       # MetLife Stadium
    "PHI00": (39.9008, -75.1675, "outdoors"),       # Lincoln Financial Field
    "PHO00": (33.5276, -112.2626, "retractable"),   # State Farm Stadium
    "PIT00": (40.4468, -80.0158, "outdoors"),       # Acrisure Stadium
    "SEA00": (47.5952, -122.3316, "outdoors"),      # Lumen Field
    "SFO01": (37.4033, -121.9694, "outdoors"),      # Levi's Stadium
    "TAM00": (27.9759, -82.5033, "outdoors"),       # Raymond James Stadium
    "VEG00": (36.0909, -115.1833, "dome"),          # Allegiant Stadium
    "WAS00": (38.9076, -76.8645, "outdoors"),       # Northwest Stadium
    # international
    "LON00": (51.5560, -0.2795, "outdoors"),        # Wembley
    "LON02": (51.6043, -0.0664, "outdoors"),        # Tottenham Hotspur Stadium
    "MAD01": (40.4531, -3.6883, "retractable"),     # Bernabeu
    "MEL00": (-37.8200, 144.9834, "outdoors"),      # Melbourne Cricket Ground
    "MEX00": (19.3029, -99.1505, "outdoors"),       # Estadio Banorte (Azteca)
    "MUN01": (48.2188, 11.6247, "outdoors"),        # Allianz Arena
    "PAR00": (48.9245, 2.3601, "outdoors"),         # Stade de France
    "RIO00": (-22.9122, -43.2302, "outdoors"),      # Maracana
}

# WMO weather codes that mean frozen precipitation. Open-Meteo also reports
# snowfall in inches, which is what the model reads; the code is for the word.
SNOW_CODES = {71, 73, 75, 77, 85, 86}


def _roof(game: dict) -> tuple[bool, str]:
    """(indoor?, label). The file's word wins when it has one."""
    roof = (game.get("roof") or "").strip().lower()
    if roof in ("dome", "closed"):
        return True, "dome" if roof == "dome" else "roof closed"
    if roof in ("outdoors", "open"):
        return False, roof
    venue = VENUES.get(game.get("stadium_id", ""))
    default = venue[2] if venue else "outdoors"
    if default == "retractable":
        return True, "roof tbd"
    if default == "dome":
        return True, "dome"
    return False, "outdoors"


def _kickoff(game: dict) -> dt.datetime | None:
    try:
        d = dt.date.fromisoformat(game.get("gameday", ""))
        h = int((game.get("gametime") or "13:00").split(":")[0])
    except ValueError:
        return None
    return dt.datetime(d.year, d.month, d.day, h)


def _fetch(points: list[tuple[float, float]]) -> list[dict]:
    """One request, one forecast per point, in kickoff order."""
    q = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        "hourly": ",".join(FIELDS),
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        # nfldata's gametime is Eastern, so ask for the hours in Eastern and
        # the game's index in the list is just its kickoff hour.
        "timezone": "America/New_York",
        "forecast_days": FORECAST_DAYS,
    }
    url = API + "?" + urllib.parse.urlencode(q, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": common.UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else [data]


def _window(hourly: dict, kickoff: dt.datetime) -> dict | None:
    """The game window out of one venue's hourly series."""
    times = hourly.get("time") or []
    stamp = kickoff.strftime("%Y-%m-%dT%H:00")
    try:
        i = times.index(stamp)
    except ValueError:
        return None
    sl = slice(i, i + GAME_HOURS)

    def col(key: str) -> list[float]:
        return [float(v) for v in (hourly.get(key) or [])[sl] if v is not None]

    wind, gust = col("wind_speed_10m"), col("wind_gusts_10m")
    temp, feels = col("temperature_2m"), col("apparent_temperature")
    prob, rain, snow = col("precipitation_probability"), col("precipitation"), col("snowfall")
    codes = col("weather_code")
    if not wind or not temp:
        return None
    return {
        "wind": sum(wind) / len(wind),           # sustained, over the game
        "gust": max(gust) if gust else 0.0,
        "temp": temp[0],                          # at kickoff
        "feels": feels[0] if feels else temp[0],
        "precip_prob": max(prob) if prob else 0.0,
        "precip": sum(rain),                      # inches over the game
        "snow": sum(snow),
        "snowing": bool(codes) and int(codes[0]) in SNOW_CODES,
    }


def _build(games: list[dict]) -> dict[str, dict | None]:
    now = dt.datetime.now()
    today = now.date()
    out: dict[str, dict | None] = {}
    todo: list[tuple[str, tuple[float, float], dt.datetime]] = []

    for g in games:
        indoor, label = _roof(g)
        kick = _kickoff(g)
        if kick is None or kick.date() < today:
            out[g["game_id"]] = None                  # played, or no date
            continue
        if indoor:
            out[g["game_id"]] = {"indoor": True, "roof": label, "priced": False}
            continue
        venue = VENUES.get(g.get("stadium_id", ""))
        if venue is None:
            out[g["game_id"]] = None                  # nowhere to point the forecast
            continue
        todo.append((g["game_id"], (venue[0], venue[1]), kick))

    if not todo:
        return out

    points = sorted({p for _, p, _ in todo})
    results = _fetch(points)
    by_point = {p: r for p, r in zip(points, results)}

    for gid, point, kick in todo:
        hourly = (by_point.get(point) or {}).get("hourly") or {}
        wx = _window(hourly, kick)
        if wx is None:
            out[gid] = None
            continue
        days_out = (kick - now).total_seconds() / 86400
        wx.update({
            "indoor": False,
            "roof": "outdoors",
            "days_out": round(days_out, 1),
            "priced": days_out <= HORIZON_DAYS,
            "fetched": now.strftime("%Y-%m-%d %H:%M"),
        })
        out[gid] = wx
    return out


def forecasts(season: int, week: int,
              max_age_hours: float = FORECAST_HOURS) -> dict[str, dict | None]:
    """{game_id: weather} for one week. Indoor games carry {"indoor": True};
    games already played, or with nowhere to point a forecast, carry None.

    Memoised on disk like the lines are. A failed pull serves the last good
    copy; with no copy at all it raises, and the caller decides whether a
    board without weather is still a board (it is).
    """
    games = [g for g in nflverse.schedule(season) if g["week"] == week]
    return common.cached_json(f"weather_{season}_w{week}.json", max_age_hours,
                              lambda: _build(games))


# --------------------------------------------------------------------------
# words for the header
# --------------------------------------------------------------------------
def describe(wx: dict | None) -> str:
    """"16 mph wind, gusts 22 · 67°F" -- what the matchup bar says."""
    if not wx:
        return ""
    if wx.get("indoor"):
        return wx.get("roof") or "indoors"
    bits = []
    wind, gust = wx.get("wind", 0.0), wx.get("gust", 0.0)
    if wind >= 8:
        s = f"{wind:.0f} mph wind"
        if gust >= 20 and gust >= wind + 6:
            s += f", gusts {gust:.0f}"
        bits.append(s)
    else:
        bits.append("calm")
    if wx.get("snow", 0.0) >= 0.1 or wx.get("snowing"):
        bits.append("snow")
    elif wx.get("precip_prob", 0.0) >= 40:
        bits.append(f"rain {wx['precip_prob']:.0f}%")
    bits.append(f"{wx.get('temp', 0.0):.0f}°F")
    if not wx.get("priced"):
        bits.append("early forecast")
    return " · ".join(bits)


def mood(wx: dict | None) -> str:
    """A CSS hook: how loudly the header should say it."""
    if not wx or wx.get("indoor"):
        return "indoor"
    if wx.get("wind", 0.0) >= 15 or wx.get("snow", 0.0) >= 0.1 or wx.get("snowing"):
        return "rough"
    if wx.get("precip_prob", 0.0) >= 50 or wx.get("temp", 60.0) <= 32:
        return "wet"
    return "calm"
