# Locations

This page explains how to view and change the list of locations that Weather-Monitor tracks.

---

## Where Locations Are Defined

Locations are defined in two places, in order of priority:

1. **`config.json` file** — if this file exists in the repository, its `locations` array is used.
2. **Built-in defaults in `weather_monitor.py`** — if no config file is found, the program uses the hard-coded default list inside the script.

The default list contains **45 locations** — primarily US Army installations plus a small number of international sites in Germany, Japan, and South Korea.

---

## The Default Location List

| Location name | Country | Notes |
|---|---|---|
| TSC HAWAII | US | |
| TSC CORPUS CHRISTI | US | |
| TSC FT POLK | US | |
| TSC FT HOOD | US | |
| TSC FT RUCKER | US | |
| TSC FT HUACHUCA | US | |
| TSC FT BLISS | US | |
| TSC HUNTER AAF | US | |
| TSC FT BENNING | US | |
| TSC WHITE SANDS | US | |
| TSC YUMA | US | |
| TSC FT GORDON | US | |
| TSC RED RIVER | US | |
| TSC ANNISTON | US | |
| TSC REDSTONE ARSENAL | US | |
| TSC FT SILL | US | |
| TSC MCALESTER | US | |
| TSC FT BRAGG | US | |
| TSC FT IRWIN | US | |
| TSC JAPAN | JP | International — uses OpenWeatherMap |
| TSC CARROLL | KR | International — uses OpenWeatherMap |
| TSC FT CAMPBELL | US | |
| TSC CP HUMPHRIES | KR | International — uses OpenWeatherMap |
| TSC FT EUSTIS | US | |
| TSC FT LEONDARDWOOD | US | |
| TSC FT KNOX | US | |
| TSC SACRAMENTO | US | |
| TSC FT CARSON | US | |
| TSC FT MEADE | US | |
| TSC FT RILEY | US | |
| TSC ABERDEEN | US | |
| TSC LETTERKENNY | US | |
| TSC FT DIX | US | |
| TSC DUGWAY | US | |
| TSC TOBYHANNA | US | |
| TSC ROCK ISLAND | US | |
| TSC WARREN | US | |
| TSC FT DRUM | US | |
| TSC JBLM FT LEWIS | US | |
| LAB NUCLEAR REF | DE | International — uses OpenWeatherMap |
| TSC KAISERSLAUTERN | DE | International — uses OpenWeatherMap |
| TSC ILLESHEIM | DE | International — uses OpenWeatherMap |
| TSC VILSECK | DE | International — uses OpenWeatherMap |
| TSC WIESBADEN | DE | International — uses OpenWeatherMap |
| TSC WAINWRIGHT | US | Alaska |

---

## How to Add a Location

### Step 1 — Find the coordinates

1. Go to [Google Maps](https://maps.google.com).
2. Find your location on the map.
3. Right-click on the exact spot.
4. The coordinates appear at the top of the menu (two numbers: latitude, longitude). Click them to copy.

For example, clicking on Fort Campbell shows something like `36.6663, -87.4830`.

### Step 2 — Edit config.json

If you are using a `config.json` file in the repository, open it and add a new entry to the `locations` array:

```json
{
  "name": "My New Location",
  "lat": 36.6663,
  "lon": -87.4830,
  "country": "US"
}
```

**Fields explained:**

| Field | Required | What it means |
|---|---|---|
| `name` | Yes | A human-readable label that appears in emails and logs. |
| `lat` | Yes | Latitude — the first number from Google Maps. |
| `lon` | Yes | Longitude — the second number from Google Maps (negative for most of the US). |
| `country` | Yes | Two-letter country code. Use `US` for all United States locations. Use `DE` for Germany, `JP` for Japan, `KR` for South Korea, etc. |
| `priority_weight` | No | Optional whole-site priority multiplier. Default is `1.0`. Use `2.0` to double the score for a generally critical site. |
| `weight` | No | Older name for `priority_weight`. Still supported, but `priority_weight` is the preferred field. |
| `hazard_weights` | No | Optional per-hazard multipliers. Use this when one weather risk matters more at a specific site. |
| `operational_vulnerabilities` | No | Optional list of plain-language site concerns, such as HVAC issues or flood-prone access roads. |
| `leadership_note` | No | Optional one-line note to explain why the site deserves extra attention. |

### Step 3 — Redeploy

If you are running on Railway, push your changes to GitHub and Railway will automatically redeploy. If you are using GitHub Actions only, the next run picks up the change immediately.

---

## How to Remove a Location

Open `config.json` and delete the entire `{ ... }` block for the location you want to remove. Be careful to leave the rest of the JSON valid (no trailing commas after the last item in a list).

---

## US vs. International Locations

| Country code | Alert source | API key needed? |
|---|---|---|
| `US` | National Weather Service (NWS) — free, official | No |
| Anything else | OpenWeatherMap | Yes — `OPENWEATHERMAP_API_KEY` |

US locations generally get richer alert data because NWS provides detailed zone and point-based alert information. International locations rely on OpenWeatherMap's alert coverage, which varies by country.

---

## How to Find Coordinates for Any City

**Google Maps method:**
1. Open [maps.google.com](https://maps.google.com).
2. Search for the city or address.
3. Right-click on the map pin or the location.
4. The coordinates appear at the top of the right-click menu.

**Example coordinates for common countries:**
- Washington D.C., US: `38.8951, -77.0364`
- Frankfurt, Germany: `50.1109, 8.6821`
- Tokyo, Japan: `35.6762, 139.6503`
- Seoul, South Korea: `37.5665, 126.9780`

---

## Location Weights (Advanced)

You can assign a `priority_weight` value to a location to make it score higher in the priority ranking. This is useful when some sites are more operationally critical than others.

```json
{
  "name": "Critical HQ Site",
  "lat": 38.9,
  "lon": -77.0,
  "country": "US",
  "priority_weight": 2.0
}
```

A weight of `2.0` doubles the priority score. A weight of `0.5` halves it. Scores are always capped at 100.

If no weight is specified, it defaults to `1.0`.

## Hazard Weights and Operational Vulnerabilities

If a location has a special operating condition, you can make the related weather hazard count more.

Example: a site with unstable HVAC and temperature-sensitive work can treat heat as more important than normal.

```json
{
  "name": "Temperature Controlled Site",
  "lat": 35.0,
  "lon": -90.0,
  "country": "US",
  "priority_weight": 1.25,
  "hazard_weights": {
    "Extreme Heat/Cold": 2.0,
    "Flooding": 0.5
  },
  "operational_vulnerabilities": [
    "HVAC unstable",
    "Work requires a steady 68 degree indoor environment"
  ],
  "leadership_note": "Heat should be treated as a higher operational concern until HVAC repairs are complete."
}
```

### What this example means

- `priority_weight` makes the entire site a little more important overall.
- `hazard_weights` makes heat count more than usual and flood risk count less than usual.
- `operational_vulnerabilities` records the real-world issue behind the weighting.
- `leadership_note` gives a short explanation that can be shown in summaries.
