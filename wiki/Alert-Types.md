# Alert Types

Weather-Monitor watches for a specific set of weather events. This page lists every alert type it recognises, what each one means in plain language, and what severity level is typically associated with it.

---

## How Alerts Are Matched

The system uses the **National Weather Service (NWS)** alert type names. It checks whether any of the names below appear anywhere in the NWS event text (it is not case-sensitive and allows extra words, so "Tornado Warning for Northern Counties" would still match "Tornado Warning").

If an alert type is NOT in this list, it is silently ignored. This filters out routine, low-impact NWS messages that would generate unnecessary noise.

---

## Full Alert Type List

### Tornadoes
| Alert type | What it means |
|---|---|
| **Tornado Warning** | A tornado has been sighted or detected on radar. Take shelter immediately. |
| **Tornado Watch** | Conditions are favourable for tornadoes. Be ready to take shelter quickly. |

### Thunderstorms
| Alert type | What it means |
|---|---|
| **Severe Thunderstorm Warning** | A severe thunderstorm with dangerous wind or large hail has been detected on radar. |
| **Severe Thunderstorm Watch** | Conditions are favourable for severe thunderstorms. |

### Flooding
| Alert type | What it means |
|---|---|
| **Flash Flood Warning** | Flash flooding is occurring or imminent. Move to higher ground immediately. |
| **Flash Flood Watch** | Flash flooding is possible. Be prepared to move quickly. |
| **Flood Warning** | Flooding is occurring or expected soon in the area. |
| **Flood Watch** | Conditions are favourable for flooding. Monitor the situation. |

### Winter Weather
| Alert type | What it means |
|---|---|
| **Winter Storm Warning** | Severe winter conditions (heavy snow, ice, blizzard) are expected. |
| **Winter Storm Watch** | Severe winter conditions are possible within 2 days. |
| **Blizzard Warning** | Blizzard conditions (heavy snow + high wind) are expected. Dangerous travel. |
| **Ice Storm Warning** | Significant ice accumulation from freezing rain is expected. |
| **Lake Effect Snow Warning** | Heavy snow from lake-effect storms is expected (typically near Great Lakes). |
| **Heavy Snow Warning** | Significant snowfall is expected. |
| **Heavy Snow Watch** | Significant snowfall is possible within 2 days. |
| **Winter Weather Advisory** | Wintry conditions (light snow, sleet, freezing drizzle) may cause hazardous travel. |

### Extreme Heat and Cold
| Alert type | What it means |
|---|---|
| **Excessive Heat Warning** | Dangerously hot and humid conditions are expected. High risk of heat-related illness. |
| **Heat Advisory** | Hot conditions are expected that could cause heat-related illness if precautions are not taken. |
| **Extreme Cold Warning** | Dangerously cold conditions are expected. Risk of frostbite and hypothermia. |
| **Extreme Cold Watch** | Dangerously cold conditions are possible within 2 days. |

### Hurricanes and Tropical Storms
| Alert type | What it means |
|---|---|
| **Hurricane Warning** | Hurricane conditions (sustained winds ≥ 74 mph) are expected within 36 hours. |
| **Hurricane Watch** | Hurricane conditions are possible within 48 hours. |
| **Tropical Storm Warning** | Tropical storm conditions (sustained winds 39–73 mph) are expected within 36 hours. |
| **Tropical Storm Watch** | Tropical storm conditions are possible within 48 hours. |

### Wind
| Alert type | What it means |
|---|---|
| **High Wind Warning** | Damaging winds are expected (typically sustained ≥ 40 mph or gusts ≥ 58 mph). |
| **High Wind Watch** | Damaging winds are possible within 2 days. |
| **Wind Advisory** | Nuisance winds that could affect operations (typically gusts 35–57 mph). |

### Fire Weather
| Alert type | What it means |
|---|---|
| **Red Flag Warning** | Critical fire weather conditions are occurring or expected: low humidity, high wind, and dry vegetation. |
| **Extreme Fire Danger** | Extreme risk of wildfire spread. |

### Air Quality
| Alert type | What it means |
|---|---|
| **Air Quality Alert** | Air quality is unhealthy. Sensitive groups (elderly, children, those with respiratory conditions) should limit outdoor exposure. |

### Avalanche
| Alert type | What it means |
|---|---|
| **Avalanche Warning** | Dangerous avalanche conditions exist. Avoid avalanche terrain. |

---

## Forecast Risk Categories

In addition to official NWS alerts, the system also scans the NWS **24-hour text forecast** for risk keywords. These categories do not require an active alert to be triggered — they are based on the forecast language itself.

| Category | Example keywords in forecast text |
|---|---|
| Severe Thunderstorms | "severe thunderstorm", "damaging wind", "large hail", "tornado" |
| Flooding | "flash flood", "flooding", "flood", "excessive rainfall", "heavy rain" |
| Winter Weather | "winter storm", "blizzard", "snow", "ice", "freezing rain", "sleet", "wind chill" |
| Extreme Heat/Cold | "heat index", "dangerous heat", "extreme heat", "extreme cold", "hard freeze" |
| High Wind | "high wind", "wind advisory", "strong winds", "gust" |
| Fire Weather | "red flag", "fire weather", "critical fire", "dry and windy" |
| Poor Air Quality | "air quality", "smoke", "ozone", "unhealthy air" |

These forecast risks appear in the daily digest email and contribute to the priority score, but they do not trigger an immediate escalation email on their own.

---

## Alert Severity Levels

NWS assigns each alert a severity level. The scoring engine uses these levels to calculate priority scores.

| Severity | Examples | Priority score contribution |
|---|---|---|
| Extreme | Tornado Warning (active tornado) | +50 per alert |
| Severe | Most Warnings | +35 per alert |
| Moderate | Most Watches and Advisories | +20 per alert |
| Minor | Advisories | +10 per alert |

The exact contribution depends on the weights configured. See [Configuration](Configuration) for details.
