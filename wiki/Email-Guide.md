# Email Guide

This page explains what emails you will receive, when each type is sent, and what the content means.

---

## Types of Emails

There are four email types the system can send:

| Type | Subject line | When it is sent |
|---|---|---|
| [Test email](#test-email) | ✅ Weather Monitor - Test Alert | When you manually trigger a test run |
| [Daily digest](#daily-digest-email) | 📊 Weather Monitor - 24h Risk Digest (N locations) | Once per day at the configured UTC hour |
| [Immediate escalation](#immediate-escalation-email) | 🚨 Weather Monitor - Immediate Escalation Alert (N locations) | When any active alert worsens |
| [Run summary](#run-summary-email) | 🚨 Weather Monitor - Run Summary (N new alerts) | When new alerts are detected (legacy mode) |

---

## Test Email

**When it arrives:** Only when you manually trigger the workflow with "Send test alert email" set to `true`.

**What it confirms:**
- The email system is connected and working.
- Your API key, Gmail credentials, and recipient addresses are correctly configured.
- The system is ready to send real alerts.

**What to do:** If you received this email, setup is complete. If not, see [Troubleshooting](Troubleshooting).

---

## Daily Digest Email

**Subject:** `📊 Weather Monitor - 24h Risk Digest (N locations)`

**When it arrives:** Once per day, at the UTC hour you configured (`DAILY_DIGEST_HOUR_UTC`, default 11:00 UTC).

**What it contains:**
- A count of how many monitored locations have elevated weather risk in the next 24 hours.
- For each at-risk location: the risk categories identified (e.g., "Flooding", "Severe Thunderstorms"), the timeframe, and a short description of what the forecast says.

**Example body:**
```
WEATHER MONITOR - 24 HOUR RISK DIGEST
==================================================

Time: 2026-07-25 11:00:00 UTC
Locations with elevated risk: 2

1. TSC FT CAMPBELL
   Risks: Severe Thunderstorms, Flooding
   Timeframe: Jul 25 18:00 UTC to Jul 26 06:00 UTC
   - Severe Thunderstorms: Tonight - Severe thunderstorms likely with damaging wind and large hail.
   - Flooding: Tonight - Heavy rain may cause flash flooding overnight.

2. TSC FT BRAGG
   Risks: High Wind
   Timeframe: Jul 25 14:00 UTC to Jul 25 22:00 UTC
   - High Wind: This Afternoon - Strong gusty winds up to 45 mph expected.
```

**When it is skipped:** If no locations have elevated risk AND `DIGEST_SEND_IF_EMPTY` is `false` (the default), no digest is sent that day. This keeps your inbox quiet on good-weather days.

---

## Immediate Escalation Email

**Subject:** `🚨 Weather Monitor - Immediate Escalation Alert (N locations)`

**When it arrives:** Any time a run detects that an active weather alert at one or more locations has worsened compared to the previous run. "Worsening" means:
- A brand-new alert event appears (something that was not there 15 minutes ago).
- A Watch upgrades to a Warning.
- The maximum severity level at a location increases (for example, from Moderate to Severe).

**What it contains:**
- The number of affected locations.
- For each location: the event type, and the full alert text from NWS (including effective and expiry times and the area description).

**Example body:**
```
WEATHER MONITOR - IMMEDIATE ESCALATION ALERT
==================================================

Time: 2026-07-25 14:32:00 UTC
Locations with escalations: 1

1. TSC FT CAMPBELL
   Event: Tornado Warning
   Tornado Warning (Severe)
   NWS Paducah issued a Tornado Warning for Fort Campbell.
   Effective: 2026-07-25T14:30:00-05:00 | Expires: 2026-07-25T15:00:00-05:00
```

**What to do when you receive this:** Read the event type and area. Refer to the [Alert Types](Alert-Types) page for what each type means and what response it warrants. The priority scoring engine also generates a recommended action — check `dashboard_digest.json` for the full structured output.

---

## Run Summary Email

This is an earlier-style email that lists all newly seen NWS alerts in a single run, regardless of whether they represent an escalation. It fires only when `IMMEDIATE_ESCALATION_ONLY` is set to `false`.

The default setting (`IMMEDIATE_ESCALATION_ONLY = true`) means this email type is not used in normal operation. Most users should leave the default in place to avoid alert fatigue.

---

## Why Am I Not Getting Emails?

If you expect to receive an alert but did not, the most common reasons are:

1. **No elevated risk was found.** The system is working normally — there may genuinely be nothing to report. Check `alerts.log` (visible in GitHub Actions run output) to see what was found.
2. **The digest was already sent today.** Only one digest per day is sent per calendar date (UTC).
3. **The alert is a repeat.** If an alert was already reported in a previous run, it will not be reported again unless it worsens.
4. **The email went to spam.** Check your spam/junk folder.
5. **Email credentials are wrong.** Re-run the test workflow to verify.

See [Troubleshooting](Troubleshooting) for more help.

---

## Email Timing vs. Time Zones

All times shown in emails are **UTC**. To convert to your local time:
- US Eastern (summer): subtract 4 hours (UTC−4)
- US Eastern (winter): subtract 5 hours (UTC−5)
- US Central (summer): subtract 5 hours
- US Pacific (summer): subtract 7 hours

For example, 11:00 UTC = 7:00 AM US Eastern time (summer).
