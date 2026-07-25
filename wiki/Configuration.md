# Configuration

Every setting in Weather-Monitor can be controlled through **environment variables**. When you are running on Railway or GitHub Actions, you set these in the dashboard or in your repository Secrets. When running locally, you can put them in a `config.json` file instead.

---

## Required Settings

These must be set or the program will not start.

| Setting name | Where to set it | What it does |
|---|---|---|
| `OPENWEATHERMAP_API_KEY` | GitHub Secret / env var | Your API key from OpenWeatherMap. Required for international locations. |
| `SENDER_EMAIL` | GitHub Secret / env var | The Gmail address that sends the alert emails. |
| `SENDER_PASSWORD` | GitHub Secret / env var | The 16-character Gmail app password (not your regular password). |
| `RECIPIENT_EMAILS` | GitHub Secret / env var | One or more email addresses to receive alerts, separated by commas. |

---

## Optional Email Behaviour Settings

These let you control when and how emails are sent.

| Setting name | Default | What it does |
|---|---|---|
| `DAILY_DIGEST_ENABLED` | `true` | Set to `false` to turn off the daily summary email entirely. |
| `DAILY_DIGEST_HOUR_UTC` | `11` | The UTC hour (0–23) when the daily digest is sent. 11 UTC = 7 AM US Eastern. |
| `DIGEST_SEND_IF_EMPTY` | `false` | If `true`, the digest email is sent even when no elevated risk is found. If `false` (recommended), it is skipped on quiet days. |
| `IMMEDIATE_ALERTS_ENABLED` | `true` | Set to `false` to stop all immediate escalation emails. |
| `IMMEDIATE_ESCALATION_ONLY` | `true` | If `true` (recommended), immediate emails are only sent when an alert *worsens*. If `false`, an email is sent for every newly seen alert. |

### What is UTC?
UTC is a global standard time with no daylight saving. Common offsets from UTC:
- US Eastern: UTC−5 (winter) / UTC−4 (summer)
- US Central: UTC−6 / UTC−5
- US Pacific: UTC−8 / UTC−7

So if you want your digest at 8 AM US Eastern (summer), set `DAILY_DIGEST_HOUR_UTC` to `12`.

---

## File Paths (Optional)

| Setting name | Default | What it does |
|---|---|---|
| `CONFIG_PATH` | `config.json` | Path to a JSON config file. Used in GitHub Actions to point at `config.example.json`. |
| `DASHBOARD_DIGEST_FILE` | `dashboard_digest.json` | Where the machine-readable run summary is written each cycle. |

---

## NWS API Settings (Optional)

The National Weather Service (NWS) API is free and requires no key. These settings let you fine-tune its behaviour.

| Setting name | Default | What it does |
|---|---|---|
| `NWS_CONTACT` | `ALF1958` | A contact token (your email or GitHub username) included in the NWS request header. NWS asks callers to identify themselves. Setting this to your email is polite and recommended. |
| `NWS_CACHE_TTL_HOURS` | `24` | How long NWS zone/grid data is cached before re-fetching. 24 hours is the safe default. |

---

## Priority Scoring Thresholds (Advanced)

The scoring engine assigns each location a numeric priority from 0 to 100. These three settings control where the band labels switch.

| Setting name | Default | Meaning |
|---|---|---|
| `PRIORITY_CRITICAL_MIN` | `85` | Score ≥ this → **critical** band |
| `PRIORITY_HIGH_MIN` | `65` | Score ≥ this → **high** band |
| `PRIORITY_MEDIUM_MIN` | `40` | Score ≥ this → **medium** band |

Scores below `PRIORITY_MEDIUM_MIN` are labelled **low**.

---

## Scoring Weights (Very Advanced)

If you want to tune how the numeric score is calculated, you can override the individual weight values. These are all whole numbers.

| Setting name | Default | Meaning |
|---|---|---|
| `WEIGHT_SEVERITY_EXTREME` | `50` | Points added per alert with severity "Extreme" |
| `WEIGHT_SEVERITY_SEVERE` | `35` | Points added per alert with severity "Severe" |
| `WEIGHT_SEVERITY_MODERATE` | `20` | Points added per alert with severity "Moderate" |
| `WEIGHT_SEVERITY_MINOR` | `10` | Points added per alert with severity "Minor" |
| `WEIGHT_EVENT_TORNADO_WARNING` | `35` | Bonus points for a Tornado Warning |
| `WEIGHT_EVENT_HURRICANE_WARNING` | `35` | Bonus points for a Hurricane Warning |
| `WEIGHT_EVENT_FLASH_FLOOD_WARNING` | `28` | Bonus points for a Flash Flood Warning |
| `WEIGHT_EVENT_TSTORM_WARNING` | `24` | Bonus points for a Severe Thunderstorm Warning |
| `WEIGHT_EVENT_BLIZZARD_WARNING` | `24` | Bonus points for a Blizzard Warning |
| `WEIGHT_EVENT_RED_FLAG_WARNING` | `20` | Bonus points for a Red Flag (Fire Weather) Warning |
| `WEIGHT_ESCALATION_BONUS` | `18` | Extra points when an alert is actively worsening |
| `WEIGHT_RISK_CAT_BONUS` | `8` | Points per forecast risk category detected |
| `WEIGHT_RISK_CAT_MAX` | `24` | Maximum points from forecast risk categories |

You do not need to change these unless the priority bands do not reflect the real-world severity you care about.

---

## Using a config.json File (Local / Advanced)

When running on your own computer, you can create a `config.json` file instead of setting environment variables. All keys use lowercase with underscores.

```json
{
  "openweathermap_api_key": "YOUR_KEY_HERE",
  "sender_email": "you@gmail.com",
  "sender_password": "your16charpassword",
  "recipient_emails": ["alerts@yourteam.com"],
  "nws_contact": "your.email@example.com",
  "daily_digest_enabled": true,
  "daily_digest_hour_utc": 11,
  "digest_send_if_empty": false,
  "immediate_alerts_enabled": true,
  "immediate_escalation_only": true,
  "locations": [
    { "name": "My Location", "lat": 35.0, "lon": -90.0, "country": "US" }
  ]
}
```

> ⚠️ **Never commit a config.json with real passwords or API keys to GitHub.** Use GitHub Secrets instead (see [Getting Started](Getting-Started)).

If both a config file and an environment variable exist for the same setting, the **environment variable wins**.
