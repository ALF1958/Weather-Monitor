# GitHub Actions

This page explains how the automated scheduler works and how to manage it.

---

## What Is GitHub Actions?

GitHub Actions is a free service built into GitHub. It can run code automatically on a schedule, without needing a separate server or computer to be on. Weather-Monitor uses it to check weather every 15 minutes around the clock.

Think of it as an alarm clock that wakes up the monitor every 15 minutes, runs it, and then goes back to sleep.

---

## The Workflow File

The automation is defined in `.github/workflows/schedule.yml`. You do not normally need to edit this file, but here is what it contains:

```yaml
name: Weather Monitor - scheduled

on:
  schedule:
    - cron: '*/15 * * * *'   # runs every 15 minutes
  workflow_dispatch:          # also allows manual runs
    inputs:
      test_mode:
        description: 'Send test alert email'
        required: false
        default: 'false'
        type: choice
        options:
          - 'false'
          - 'true'
```

The `cron: '*/15 * * * *'` line means "run every 15 minutes". A cron expression is a standard way to describe a recurring schedule.

---

## How to View Recent Runs

1. Go to your repository on GitHub.
2. Click the **Actions** tab at the top.
3. In the left sidebar, click **Weather Monitor - scheduled**.
4. You will see a list of recent runs. A green tick (✅) means success. A red X (❌) means something went wrong.
5. Click any run to see its log output.

---

## How to Trigger a Manual Run

You can run the monitor immediately without waiting 15 minutes:

1. Go to **Actions** → **Weather Monitor - scheduled**.
2. Click **Run workflow** (the button on the right side).
3. Set **Send test alert email** to:
   - `false` — runs normally (checks weather, sends alerts if warranted)
   - `true` — sends a test email confirming the email system works
4. Click the green **Run workflow** button.

---

## How to Pause the Monitor

If you want to stop the automatic runs temporarily:

1. Go to **Actions** → **Weather Monitor - scheduled**.
2. Click the three dots (⋯) menu near the top-right.
3. Click **Disable workflow**.

To re-enable it, go back to the same place and click **Enable workflow**.

---

## Understanding the Run Log

When you click on a run, you will see a step-by-step log. The most useful section is **Run weather monitor**. Here is how to read it:

| Log message | What it means |
|---|---|
| `Starting weather alert check for multiple locations...` | The run has started. |
| `Checking alerts for [name] (US)...` | It is checking a US location. |
| `Found N alerts for [name]` | Active NWS alerts were found. |
| `Critical alert identified: [event] for [area]` | A matching alert type was found. |
| `24h risk digest email sent with N elevated-risk locations` | Digest email was sent. |
| `Immediate escalation email sent with N alert entries` | An escalation email was sent. |
| `No elevated weather risks...` | No risks found — this is normal on quiet days. |
| `OPENWEATHERMAP_API_KEY not set` | The API key secret is missing. |
| `Email credentials not set` | The SENDER_EMAIL or SENDER_PASSWORD secret is missing. |

---

## GitHub Actions Limits (Free Tier)

GitHub's free plan includes **2,000 minutes per month** of Actions run time. Each Weather-Monitor run takes roughly 1–3 minutes. At 96 runs per day (every 15 minutes), this comes to about 3,000–9,000 minutes per month — **which exceeds the free limit**.

### What This Means for You

If you hit the limit, GitHub will pause the workflow for the rest of the month. When this happens, you have a few options:

1. **Change the schedule to every 30 minutes.** Edit `.github/workflows/schedule.yml` and change `*/15` to `*/30`. This halves the run count and should stay within the free limit.
2. **Deploy to Railway.** Railway runs the script on its own server instead of using GitHub Actions minutes. See [Getting Started](Getting-Started) for setup instructions. Railway's free tier should cover the 15-minute schedule.
3. **Upgrade GitHub.** Paid GitHub plans include more minutes.

### How to Change the Schedule

Open `.github/workflows/schedule.yml` and find this line:
```yaml
    - cron: '*/15 * * * *'
```

Change it to run every 30 minutes:
```yaml
    - cron: '*/30 * * * *'
```

Or every hour:
```yaml
    - cron: '0 * * * *'
```

Save the file, commit, and push. The new schedule takes effect on the next trigger.

---

## How Secrets Are Passed to the Workflow

The workflow file passes your GitHub Secrets to the program as environment variables:

```yaml
env:
  OPENWEATHERMAP_API_KEY: ${{ secrets.OPENWEATHERMAP_API_KEY }}
  SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
  SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
  RECIPIENT_EMAILS: ${{ secrets.RECIPIENT_EMAILS }}
```

The `${{ secrets.NAME }}` syntax tells GitHub Actions to look up the secret by name and inject it. The actual value is never shown in logs — it is masked automatically.

---

## Troubleshooting Failed Runs

If a run shows a red X:

1. Click the failed run.
2. Click the **Run weather monitor** step to expand the log.
3. Look for error messages near the bottom of the log.
4. Compare against the [Troubleshooting](Troubleshooting) page.
