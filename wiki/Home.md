# Weather-Monitor Wiki

Welcome to the Weather-Monitor project wiki! This is your complete guide to understanding, setting up, and using the system.

---

## What Does This Project Do?

Weather-Monitor is an automated system that watches for dangerous weather at multiple locations and sends your team email alerts when conditions worsen. It runs every 15 minutes in the cloud — no computer needs to stay on.

**In plain terms:** You tell it where to watch. It checks official weather data. It emails you when something serious is happening.

---

## Wiki Pages

| Page | What you'll find there |
|------|------------------------|
| [Getting Started](Getting-Started) | How to set up the system from scratch (start here!) |
| [Configuration](Configuration) | Every setting explained in plain language |
| [How It Works](How-It-Works) | What the program actually does each time it runs |
| [Alert Types](Alert-Types) | The full list of weather events the system watches for |
| [Email Guide](Email-Guide) | What emails get sent, when, and what they look like |
| [Locations](Locations) | How to add, remove, or adjust monitored locations |
| [GitHub Actions](GitHub-Actions) | How the automated 15-minute schedule works |
| [Troubleshooting](Troubleshooting) | Fixes for the most common problems |

---

## Quick Facts

- Monitors **US locations** using the free National Weather Service (NWS) API — no key needed for US alerts.
- Monitors **international locations** (Japan, Korea, Germany, etc.) using the OpenWeatherMap API (free key required).
- Sends a **daily digest email** once per day summarising any elevated risk across all locations (default time: 11:00 UTC).
- Sends an **immediate escalation email** only when an active alert suddenly gets worse — this keeps your inbox quiet.
- Runs automatically via **GitHub Actions** every 15 minutes. No server or hosting is needed beyond Railway or similar free-tier cloud, or you can run it entirely on GitHub Actions.
- All settings can be controlled through **environment variables**, so no sensitive information needs to be stored in a file.

---

## Where to Start

If you are setting up for the first time, go straight to the [Getting Started](Getting-Started) page.

If the system is already running and you want to change something, see the [Configuration](Configuration) page.

If you are getting unexpected results or no emails, see the [Troubleshooting](Troubleshooting) page.
