# Getting Started

This page walks you through setting up Weather-Monitor from scratch. Expect it to take about 30 minutes the first time.

---

## Before You Begin

You will need:
- A **GitHub account** (free) — you already have one since you are reading this.
- A **Gmail account** to send the alert emails from. This does not have to be your main email.
- An **OpenWeatherMap API key** (free) — required for non-US locations. US-only monitoring works without it, but the startup check still validates that the key is present, so get one anyway.

---

## Step 1 — Get a Free OpenWeatherMap API Key (5 minutes)

OpenWeatherMap is the weather data service used for international locations.

1. Go to [https://openweathermap.org/api](https://openweathermap.org/api).
2. Click **Sign Up** and create a free account.
3. Verify your email address.
4. Go to [https://home.openweathermap.org/api_keys](https://home.openweathermap.org/api_keys).
5. Copy the key shown on the page.
6. Save it somewhere safe — you will need it in Step 3.

---

## Step 2 — Set Up Gmail to Send Alerts (5 minutes)

Google requires you to create a special "app password" so that the monitor can send emails on your behalf without using your real password.

1. Go to [https://myaccount.google.com/security](https://myaccount.google.com/security).
2. Make sure **2-Step Verification** is turned on. If it is not, turn it on first.
3. After 2-Step Verification is on, go back to the Security page.
4. Find **App passwords** and click it. (If you do not see it, search for "app passwords" in your Google account.)
5. Select **Mail** as the app type.
6. Google gives you a 16-character password. Copy it.
7. Save it somewhere safe — you will need it in Step 3.

> **Note:** The app password is different from your regular Gmail password. It is specifically for this kind of automated use.

---

## Step 3 — Add Your Secrets to GitHub (5 minutes)

The monitor reads sensitive values (API key, email password) from **GitHub Secrets**. Secrets are stored securely and never appear in plain text anywhere.

1. Go to your repository on GitHub: `https://github.com/ALF1958/Weather-Monitor`.
2. Click **Settings** (near the top-right of the page).
3. In the left-hand menu, click **Secrets and variables** → **Actions**.
4. Click **New repository secret** and add each of the following:

| Secret name | What to put in |
|-------------|----------------|
| `OPENWEATHERMAP_API_KEY` | Your API key from Step 1 |
| `SENDER_EMAIL` | The Gmail address that will send alerts |
| `SENDER_PASSWORD` | The 16-character app password from Step 2 |
| `RECIPIENT_EMAILS` | Email address(es) to receive alerts, separated by commas |

**Example for `RECIPIENT_EMAILS`:** `alice@example.com,bob@example.com`

---

## Step 4 — Verify the Default Locations

The system comes pre-configured with a list of US military installation locations plus a few international sites. Open `weather_monitor.py` or see the [Locations](Locations) page for the full list.

If those locations are right for you, nothing needs to change. To add or remove locations, follow the [Locations](Locations) guide.

---

## Step 5 — Send a Test Email

Before waiting 15 minutes for the first automatic run, you can trigger a test immediately.

1. Go to your repository on GitHub.
2. Click **Actions** (in the top menu).
3. Click the workflow named **Weather Monitor - scheduled** in the left sidebar.
4. Click **Run workflow** (the button on the right side).
5. Set **Send test alert email** to `true`.
6. Click the green **Run workflow** button.

Within about 60 seconds, a test email will arrive in the inbox you configured. Check spam if it does not appear.

---

## Step 6 — Let It Run Automatically

Once secrets are set, the monitor runs automatically every 15 minutes via GitHub Actions. No further action is needed.

- A **daily digest** email summarizing any elevated risk arrives once per day at 11:00 UTC (configurable — see [Configuration](Configuration)).
- An **immediate escalation** email is sent any time an active warning worsens (for example, a Watch upgrades to a Warning).

---

## Next Steps

| I want to… | Go to… |
|------------|--------|
| Change when the digest is sent | [Configuration](Configuration) |
| Add more locations to monitor | [Locations](Locations) |
| Understand what the emails mean | [Email Guide](Email-Guide) |
| Something isn't working | [Troubleshooting](Troubleshooting) |
