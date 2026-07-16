# Quick Start Guide for Beginners

Your weather alert system in 5 steps. **Total time: ~30 minutes**

## Step 1: Get Free API Key (5 min)

### OpenWeatherMap
1. Go to https://openweathermap.org/api
2. Click "Sign Up" (it's free)
3. Verify email
4. Go to https://home.openweathermap.org/api_keys
5. Copy the key
6. **Save it somewhere safe** ✅

## Step 2: Set Up Gmail for Alerts (5 min)

### Enable Gmail to Send Alerts
1. Go to https://myaccount.google.com/security
2. Turn on "2-Step Verification" (if not already on)
3. After enabling 2FA, go back to Security page
4. Find "App passwords" and click it
5. Select "Mail" and "Windows Computer" (or whatever)
6. Google gives you a 16-character password
7. **Save it somewhere safe** ✅

## Step 3: Configure Your Locations & Email (5 min)

1. Open `config.json` file in the repo (or edit online on GitHub)
2. Replace these values:

```json
"openweathermap_api_key": "PASTE_YOUR_API_KEY_HERE",

"sender_email": "YOUR_GMAIL@gmail.com",
"sender_password": "YOUR_16_CHAR_PASSWORD",

"recipient_emails": [
  "team@company.com",
  "manager@company.com"
]
```

**Add your locations** - edit the `locations` array. Find coordinates from Google Maps (right-click city → coordinates).

## Step 4: Test It Works (5 min)

### Option A: Test on Your Computer
```bash
# Open Terminal/Command Prompt
# Navigate to Weather-Monitor folder

python weather_monitor.py
```

Should see: `Starting weather check for X locations...`

Check your email inbox for test alert.

### Option B: Skip Testing (Not Recommended)
Go straight to Step 5

## Step 5: Run It 24/7 on Free Cloud (5-10 min)

### Easiest Way: Railway.app

1. Go to https://railway.app
2. Click "Start Project" → "Deploy from GitHub repo"
3. Sign in with your GitHub account
4. Select `ALF1958/Weather-Monitor`
5. Railway automatically detects Python
6. Click "Deploy"
7. In Railway dashboard, add these variables:
   - `OPENWEATHERMAP_API_KEY` = your API key
   - `SENDER_EMAIL` = your Gmail
   - `SENDER_PASSWORD` = your 16-char password
   - `RECIPIENT_EMAILS` = team@company.com,manager@company.com

8. Done! ✅ Your monitor runs 24/7

---

## That's It!

Your system is now:
- ✅ Monitoring 25 locations
- ✅ Checking every 15 minutes
- ✅ Sending team email when **severe weather** happens
- ✅ Running 24/7 for free

## When You Get Alerts

1. **Severe weather happens** anywhere you're monitoring
2. **System detects it** (checks every 15 min)
3. **Your team gets email** instantly
4. **No duplicates** (tracks what was already sent)

## Severe Weather Includes

✅ Tornado  
✅ Flood  
✅ Severe Thunderstorm  
✅ Hurricane  
✅ Winter Storm  
✅ Extreme Cold/Heat  
✅ Lightning  
✅ Hail  
✅ Blizzard  

## How to Add More Locations

Need to monitor more cities?

1. Open `config.json`
2. Find coordinates on Google Maps (right-click → coordinates)
3. Add to `locations` array:
```json
{
  "name": "Bangkok, Thailand",
  "lat": 13.7563,
  "lon": 100.5018
}
```
4. Save and redeploy (Railway auto-deploys from GitHub)

## Problems?

**Not getting emails?**
- Check spam folder
- Verify Gmail app password in config.json
- Check `alerts.log` in Railway dashboard

**No alerts detected?**
- That's actually good! Means no severe weather
- System is working

**Confused about API key?**
- Watch this: https://www.youtube.com/watch?v=SGYKIBbvz7E (or similar tutorial)

---

**Your severe weather alert system is live! 🎉**

Now your team gets instant alerts when severe weather hits any of your 25 locations worldwide.

Questions? Check `alerts.log` to see what's happening.
