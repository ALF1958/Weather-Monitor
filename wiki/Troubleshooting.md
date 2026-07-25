# Troubleshooting

This page covers the most common problems and how to fix them.

---

## I Am Not Receiving Any Emails

Work through this checklist in order:

### 1. Check your spam/junk folder
Gmail-to-Gmail emails sometimes land in spam the first time. Mark the email as "Not Spam" if you find it there, and future emails should arrive in your inbox.

### 2. Send a test email to verify the setup
1. Go to **Actions** → **Weather Monitor - scheduled** on GitHub.
2. Click **Run workflow**.
3. Set **Send test alert email** to `true`.
4. Wait 60 seconds.
5. If the test email arrives → your setup is correct. Real alerts will come when weather warrants.
6. If the test email does not arrive → continue below.

### 3. Check that your GitHub Secrets are set correctly
1. Go to your repository → **Settings** → **Secrets and variables** → **Actions**.
2. Verify that all four secrets exist: `OPENWEATHERMAP_API_KEY`, `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECIPIENT_EMAILS`.
3. If any are missing or misspelled, add or correct them.

### 4. Verify the Gmail app password
The `SENDER_PASSWORD` must be a **16-character Gmail app password**, not your regular Gmail password. If you are unsure:
1. Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
2. Delete the old app password.
3. Generate a new one.
4. Update the `SENDER_PASSWORD` secret on GitHub.

### 5. Make sure 2-Step Verification is on in Gmail
Gmail app passwords only work when 2-Step Verification (also called 2-factor authentication) is enabled. Go to [https://myaccount.google.com/security](https://myaccount.google.com/security) to check.

### 6. Check the Actions log
1. Go to **Actions** → click the most recent run.
2. Click **Run weather monitor** to expand the log.
3. Look for lines starting with `ERROR` or `Failed to send`.
4. Common error messages and what they mean are in the table below.

---

## Common Error Messages

| Error message | Cause | Fix |
|---|---|---|
| `OPENWEATHERMAP_API_KEY not set` | The API key secret is missing. | Add `OPENWEATHERMAP_API_KEY` to GitHub Secrets. |
| `Email credentials not set` | `SENDER_EMAIL` or `SENDER_PASSWORD` secret is missing. | Add the missing secret. |
| `No recipient emails configured` | `RECIPIENT_EMAILS` is empty or not set. | Add `RECIPIENT_EMAILS` to GitHub Secrets. |
| `Failed to send email alert` | Gmail rejected the login or connection. | Check the app password and that 2FA is on. |
| `Authentication unsuccessful` | Wrong app password. | Generate a new Gmail app password and update the secret. |
| `Could not load config.json` | The config file is missing or has a formatting error. | Fix or remove the config file; the program will fall back to environment variables. |
| `Invalid coordinates for [name]` | A location in your config is missing lat/lon. | Add `lat` and `lon` to that location entry. |

---

## No Alerts Are Being Detected (But I Expected Some)

**This may not be a problem.** If the system runs and finds no severe weather, that is correct — it means all monitored locations are currently safe.

To confirm the system is checking weather properly:
1. Open the **Actions** log for a recent run.
2. You should see `Checking alerts for [location name] (US)...` for each location.
3. If no alerts are listed, weather is calm at all locations.

If you believe there should be active alerts that are not appearing:
- Check [https://alerts.weather.gov/](https://alerts.weather.gov/) directly to see what NWS is currently reporting.
- Make sure the affected location's coordinates are correct. A small error in latitude/longitude could place the point outside the alert zone.
- Check that the alert type is in the supported list (see [Alert Types](Alert-Types)). Some low-priority NWS messages are intentionally filtered out.

---

## The Digest Email Did Not Arrive Today

Possible reasons:
1. **No elevated risk was found.** If `DIGEST_SEND_IF_EMPTY` is `false` (the default), the digest is skipped on days with no elevated risk. That is intentional — it keeps your inbox quiet on calm days.
2. **The digest already sent today.** Only one digest per UTC calendar day is sent. If the workflow ran at midnight UTC and sent the digest, it will not send again until the next day.
3. **The digest hour has not arrived yet.** The default is 11:00 UTC. If the current UTC time is before 11:00, the digest has not fired yet today.

To check: look at the Actions log and search for `should_send_daily_digest` or `24h risk digest` to see whether the digest condition was evaluated.

---

## The Workflow Is Not Running at All

Possible causes:
1. **The workflow is disabled.** Go to **Actions** → **Weather Monitor - scheduled** → check for a "disabled" banner. Re-enable it if needed.
2. **GitHub paused the workflow due to inactivity.** If the repository has had no pushes or commits for 60 days, GitHub pauses scheduled workflows. Make a small commit (like editing the README) to reactivate it.
3. **You ran out of free GitHub Actions minutes.** See [GitHub Actions — Limits](GitHub-Actions#github-actions-limits-free-tier) for what to do.

---

## I Accidentally Committed My Password or API Key

Act quickly:
1. **Revoke the exposed credential immediately.**
   - For the OpenWeatherMap key: go to [https://home.openweathermap.org/api_keys](https://home.openweathermap.org/api_keys), delete the key, and generate a new one.
   - For the Gmail app password: go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), delete it, and create a new one.
2. **Update the GitHub Secret** with the new value.
3. **Remove the secret from the commit.** This requires rewriting Git history and is more complex. If you are not comfortable with that, the fastest safe option is to simply invalidate the old credential (step 1) so it is useless even if someone finds it in the history.

Going forward: keep secrets in GitHub Secrets only — never put them in any file that you commit.

---

## I Got an Email But I Don't Understand It

See the [Email Guide](Email-Guide) for a plain-language explanation of each email type and what to do when you receive one.

For the alert types mentioned in an escalation email, see [Alert Types](Alert-Types).

---

## I Have a Question Not Covered Here

Open an **Issue** on the GitHub repository:
1. Go to `https://github.com/ALF1958/Weather-Monitor`.
2. Click **Issues** → **New issue**.
3. Describe what you expected to happen and what actually happened.
4. Include any error message from the Actions log if relevant.
