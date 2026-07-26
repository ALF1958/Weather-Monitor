# Weather-Monitor

Weather-Monitor is a Python project for checking severe weather alerts and sending email notifications.

## Current Repository Contents
- `weather_monitor.py` - main monitoring script
- `requirements.txt` - Python dependencies
- `QUICK_START.md` - beginner setup guide
- `WORKING_AGREEMENT.md` - collaboration guide for this repository

## Copilot Collaboration Note
This repository is being developed with a beginner-friendly workflow.

- Assume the repository owner is new to programming and GitHub.
- Prefer clear recommendations over multiple open-ended choices.
- Explain proposed changes in simple terms.
- Work iteratively: assess the current state, recommend the next step, apply the smallest safe change, then re-evaluate.
- Flag gaps between documentation, configuration, and actual behavior so they can be fixed in later iterations.

## Getting Started
Use the setup steps in `QUICK_START.md`.

## Running on GitHub Actions (Recommended)

This repository includes `.github/workflows/schedule.yml`, which runs the monitor every 15 minutes and also supports manual runs.

### Why duplicate immediate emails can happen on GitHub-hosted runners

GitHub-hosted runners are **ephemeral** (temporary). Each run starts on a fresh machine.  
If state files are not restored, the monitor thinks it is the first run and can re-send immediate alerts.

The workflow now restores and saves these state files using `actions/cache`:

- `monitor_state.json`
- `sent_alerts.json`
- `nws_points_cache.json`

This keeps escalation and digest history between runs.

## Required GitHub Secrets

Set these in **Repository → Settings → Secrets and variables → Actions**:

- `OPENWEATHERMAP_API_KEY`
- `SENDER_EMAIL`
- `SENDER_PASSWORD`
- `RECIPIENT_EMAILS`
- `NWS_CONTACT` (recommended by NWS API guidance)

## Recommended Email Behavior Settings (set in workflow env)

The workflow explicitly sets:

- `DAILY_DIGEST_ENABLED=true`
- `DAILY_DIGEST_HOUR_UTC=11`
- `DIGEST_SEND_IF_EMPTY=true`
- `IMMEDIATE_ALERTS_ENABLED=true`
- `IMMEDIATE_ESCALATION_ONLY=true`

### What these mean

- `DIGEST_SEND_IF_EMPTY=true` ensures you still get one digest each UTC day even when no elevated weather risks are found.
- `IMMEDIATE_ESCALATION_ONLY=true` prevents immediate emails unless conditions actually worsen.

## Daily Digest Scheduling (UTC)

GitHub cron schedules run in **UTC**.  
`DAILY_DIGEST_HOUR_UTC` must be set to the UTC hour you want (0–23).

Example: if you want about 7 AM US Eastern during daylight saving time, use `11`.

## State Files Used by the Monitor

- `monitor_state.json` stores digest history and per-location escalation fingerprints.
- `sent_alerts.json` stores deduplication keys for already-notified alerts.
- `nws_points_cache.json` stores NWS metadata cache to reduce repeated API lookups.
- `dashboard_digest.json` is a run summary output for diagnostics and dashboards.

## More Detail

For beginner-friendly walkthroughs, see:

- `wiki/GitHub-Actions.md`
- `wiki/How-It-Works.md`
- `wiki/Configuration.md`
