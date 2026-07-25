# How It Works

This page explains what Weather-Monitor actually does each time it runs. You do not need to understand this to use the system, but it is helpful if you want to know why a particular email was (or was not) sent.

---

## The 15-Minute Cycle

GitHub Actions triggers the monitor every 15 minutes around the clock. Each run goes through these steps:

```
Load settings
    ↓
For each location: check for alerts and forecast risks
    ↓
Decide what emails to send
    ↓
Send emails (if any)
    ↓
Save state and write dashboard summary
    ↓
Done — wait for next run
```

---

## Step 1: Load Settings

The program reads all configuration from environment variables (or a config file). It validates that the required values are present. If anything essential is missing, it logs an error and stops.

---

## Step 2: Check Each Location

For every location in the list, the program does the following:

### US Locations (country = "US")

US locations use the **National Weather Service (NWS)** API — this is a free, official US government service. No API key is needed for it.

The program fetches alerts in two ways and combines the results:

1. **Zone-based lookup:** NWS divides the US into geographic "zones" (forecast zones and county zones). The program first finds which zones cover the location, then fetches active alerts for those zones. This is the most complete method.

2. **Point-based lookup:** As a backup, the program also queries alerts directly at the exact latitude/longitude. This catches any alerts that zone lookups might miss.

Results from both lookups are merged, and any duplicates are removed automatically.

It also fetches the **NWS forecast** for the next 24 hours and scans the text for risk keywords (for example: "flash flood", "blizzard", "extreme heat"). This produces a *forecast risk summary* — used for the daily digest.

### International Locations (country ≠ "US")

International locations use **OpenWeatherMap**. This requires the API key you configured. The program fetches current weather conditions and alert data from that service.

---

## Step 3: Score Each Location

After checking alerts and forecasts, the program calculates a **priority score** from 0 to 100 for each location. The score reflects how serious the current weather threat is.

The score is built from four ingredients:

| Ingredient | What it adds |
|---|---|
| Alert severity | More points for higher severity (Extreme > Severe > Moderate > Minor) |
| Event type bonus | Extra points for the most dangerous alert types (Tornado Warning, Hurricane Warning, Flash Flood Warning, etc.) |
| Forecast risk bonus | Extra points for each risk category found in the 24-hour forecast |
| Escalation bonus | Extra points if the alert is actively getting worse right now |

A location weight multiplier can be set per location if certain sites are more critical to your operations.

### Priority Bands

The final score maps to a **priority band**:

| Band | Default score range | Meaning |
|---|---|---|
| **Critical** | 85 – 100 | Severe and worsening conditions; emergency action warranted |
| **High** | 65 – 84 | Significant threat; leadership should be briefed |
| **Medium** | 40 – 64 | Elevated risk; monitor closely |
| **Low** | 0 – 39 | Normal or minor risk |

These thresholds can be adjusted — see [Configuration](Configuration).

### Status Labels

Each location also gets a **status** label:

| Status | Meaning |
|---|---|
| escalating | An active alert has just worsened this run |
| active | Active NWS alerts exist right now |
| elevated | No active alerts, but forecast shows elevated risk |
| normal | No alerts and no elevated forecast risk |

### Recommended Action

Based on the priority band and status, the program generates a plain-language action recommendation for senior management. For example:
- **Critical / escalating:** "IMMEDIATE ACTION: Activate emergency response protocol; verify personnel shelter posture and accountability now."
- **Low / normal:** "No action required; continue routine monitoring."

---

## Step 4: Decide What to Send

### Daily Digest Email

Once per day, at the configured UTC hour, the program sends a digest email listing all locations that have any elevated forecast risk in the next 24 hours.

If no locations have elevated risk and `DIGEST_SEND_IF_EMPTY` is `false` (the default), the digest is skipped that day.

The digest time is tracked in a state file (`monitor_state.json`) so it fires only once even if the program runs 96 times that day.

### Immediate Escalation Email

An immediate email is sent when an active alert at a location *worsens* between runs. "Worsening" means any of:
- A brand-new alert event appears (for example, a new Tornado Warning).
- An existing Watch upgrades to a Warning.
- The maximum severity level increases.

This keeps your inbox quiet — you are only interrupted when something gets worse, not every 15 minutes just because an alert remains active.

If `IMMEDIATE_ESCALATION_ONLY` is set to `false`, an email is sent for every newly seen alert (not just escalations). This is noisier.

---

## Step 5: Send Emails

All emails go out through Gmail via standard SMTP (a protocol for sending email). The program logs whether each send succeeded or failed.

Emails are sent using the `SENDER_EMAIL` and `SENDER_PASSWORD` you configured. Recipients are the addresses in `RECIPIENT_EMAILS`.

---

## Step 6: Save State and Write Dashboard

After every run the program saves:

- **`sent_alerts.json`** — which specific alerts have already been reported, so they are not emailed again on the next run.
- **`monitor_state.json`** — digest timing, and the fingerprint of each location's last alert state (used to detect escalation on the next run).
- **`nws_points_cache.json`** — NWS zone/grid metadata cached for up to 24 hours to reduce API calls.
- **`dashboard_digest.json`** — a machine-readable JSON summary of the full run: all location scores, priority bands, recommended actions, delivery status, and any errors. This can be read by dashboards or monitoring tools.

---

## Deduplication — Why You Won't Get Spam

The system is built to avoid sending the same alert twice:

1. Every alert has a stable **ID**. If the same alert is still active on the next run, its ID is already in `sent_alerts.json`, so no email is sent again.
2. The **daily digest** fires at most once per calendar day (UTC).
3. The **immediate escalation** fires only when something is actually *new or worse*.

These three rules together mean your inbox stays quiet unless the weather situation genuinely changes.
