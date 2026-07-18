#!/usr/bin/env python3
"""
Weather Monitor - Alerts for Severe Weather & Advisories
Monitors multiple locations and sends email alerts for severe weather conditions and official advisories
Uses National Weather Service (NWS) for US locations and OpenWeatherMap for international locations
"""

import os
import json
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('alerts.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Alert types that warrant notification (NWS)
CRITICAL_ALERT_TYPES = {
    'Tornado Warning',
    'Tornado Watch',
    'Severe Thunderstorm Warning',
    'Severe Thunderstorm Watch',
    'Flood Warning',
    'Flood Watch',
    'Flash Flood Warning',
    'Flash Flood Watch',
    'Winter Storm Warning',
    'Winter Storm Watch',
    'Extreme Cold Warning',
    'Extreme Cold Watch',
    'Excessive Heat Warning',
    'Heat Advisory',
    'Hurricane Warning',
    'Hurricane Watch',
    'Tropical Storm Warning',
    'Tropical Storm Watch',
    'High Wind Warning',
    'High Wind Watch',
    'Blizzard Warning',
    'Ice Storm Warning',
    'Lake Effect Snow Warning',
    'Avalanche Warning',
    'Extreme Fire Danger',
    'Red Flag Warning',
    'Air Quality Alert',
    'Wind Advisory',
    'Winter Weather Advisory',
    'Heavy Snow Warning',
    'Heavy Snow Watch',
}

# Track sent alerts to avoid duplicates
SENT_ALERTS_FILE = 'sent_alerts.json'

# In-memory cache for NWS points -> alerts URL to reduce /points calls per run
NWS_POINTS_CACHE = {}


def load_config():
    """Load configuration from environment variables or config.json"""
    config_path = os.getenv('CONFIG_PATH', 'config.json')
    
    # Try to load from file first
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load {config_path}: {e}")
    
    # Fallback to environment variables
    return {
        'openweathermap_api_key': os.getenv('OPENWEATHERMAP_API_KEY'),
        'sender_email': os.getenv('SENDER_EMAIL'),
        'sender_password': os.getenv('SENDER_PASSWORD'),
        'recipient_emails': os.getenv('RECIPIENT_EMAILS', '').split(','),
        # Optional contact string for NWS User-Agent: set NWS_CONTACT env var or provide in config
        'nws_contact': os.getenv('NWS_CONTACT'),
        'locations': [
            {'name': 'New York, USA', 'lat': 40.7128, 'lon': -74.0060, 'country': 'US'},
            {'name': 'London, UK', 'lat': 51.5074, 'lon': -0.1278, 'country': 'GB'},
            {'name': 'Tokyo, Japan', 'lat': 35.6762, 'lon': 139.6503, 'country': 'JP'},
            {'name': 'Sydney, Australia', 'lat': -33.8688, 'lon': 151.2093, 'country': 'AU'},
            {'name': 'Toronto, Canada', 'lat': 43.6532, 'lon': -79.3832, 'country': 'CA'},
            {'name': 'Corpus Christi, USA', 'lat': 27.5705, 'lon': -97.3964, 'country': 'US'},
            {'name': 'Fort Hood, USA', 'lat': 31.1544, 'lon': -97.8072, 'country': 'US'},
            {'name': 'Fort Campbell, USA', 'lat': 36.6260, 'lon': -87.4660, 'country': 'US'},
            {'name': 'Anniston Army Depot, USA', 'lat': 33.7344, 'lon': -85.8084, 'country': 'US'},
        ]
    }


def load_sent_alerts():
    """Load previously sent alerts to avoid duplicates"""
    if os.path.exists(SENT_ALERTS_FILE):
        try:
            with open(SENT_ALERTS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load sent alerts: {e}")
    return {}


def save_sent_alerts(alerts):
    """Save sent alerts to file"""
    try:
        with open(SENT_ALERTS_FILE, 'w') as f:
            json.dump(alerts, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save sent alerts: {e}")


def make_nws_session(contact=None):
    """Create and return a requests.Session configured for NWS API usage.

    NWS (api.weather.gov) does NOT require an API key, but requests that callers
    send a descriptive User-Agent including a contact email or URL. Provide this
    via the NWS_CONTACT env var or the config (nws_contact). If no contact is
    provided, a generic contact token is used, but it's recommended to set a
    real email or URL.
    """
    sess = requests.Session()
    contact_val = contact or os.getenv('NWS_CONTACT') or 'ALF1958'
    user_agent = f"Weather Monitor/1.0 ({contact_val})"
    headers = {
        'User-Agent': user_agent,
        'Accept': 'application/geo+json',
    }
    sess.headers.update(headers)
    return sess


def get_nws_alerts(lat, lon, location_name, session=None):
    """Fetch alerts from National Weather Service (US only).

    Uses a requests.Session with appropriate User-Agent and Accept headers.
    Caches the points -> alerts URL mapping for the lifetime of the process to
    reduce calls to /points for the same coordinates.
    """
    sess = session or make_nws_session()
    cache_key = f"{lat},{lon}"

    try:
        # Check cache for alerts URL
        alerts_url = NWS_POINTS_CACHE.get(cache_key)
        if not alerts_url:
            # Get the grid point for this location
            points_url = f"https://api.weather.gov/points/{lat},{lon}"
            points_response = sess.get(points_url, timeout=10)
            points_response.raise_for_status()
            points_data = points_response.json()

            # Get the alerts URL from the points data
            alerts_url = points_data.get('properties', {}).get('alerts')
            if not alerts_url:
                logger.info(f"No alerts URL available for {location_name}")
                return None

            # Cache the alerts URL for this lat/lon for this run
            NWS_POINTS_CACHE[cache_key] = alerts_url

        # Fetch alerts
        alerts_response = sess.get(alerts_url, timeout=10)
        alerts_response.raise_for_status()
        alerts_data = alerts_response.json()

        features = alerts_data.get('features', [])
        if features:
            logger.info(f"Found {len(features)} alerts for {location_name}")
            return features

        return None

    except requests.exceptions.RequestException as e:
        logger.warning(f"Error fetching NWS alerts for {location_name}: {e}")
        return None


def parse_nws_alerts(features):
    """Parse NWS alert features into critical alerts only"""
    alerts = []

    for feature in features:
        props = feature.get('properties', {})

        # Get alert details
        event = props.get('event', 'Unknown Alert')
        severity = props.get('severity', 'Unknown')
        headline = props.get('headline', '')
        effective = props.get('effective', '')
        expires = props.get('expires', '')

        # ONLY include critical alert types
        if event in CRITICAL_ALERT_TYPES:
            alert_text = f"{event} ({severity})"
            if headline:
                alert_text += f"\n{headline}"
            if effective or expires:
                alert_text += f"\nEffective: {effective} | Expires: {expires}"
            alerts.append(alert_text)
            logger.info(f"Critical alert identified: {event} for {props.get('areaDesc', 'Unknown area')}")
        else:
            logger.debug(f"Non-critical alert filtered out: {event}")

    return alerts if alerts else None


def send_alert_email(sender_email, sender_password, recipient_emails, location_name, conditions, alert_type='NWS Alert'):
    """Send email alert for severe weather or advisories"""
    try:
        # Create email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = f"🚨 {alert_type} - {location_name}"

        # Email body
        conditions_list = '\n'.join([f"  • {c}" for c in conditions])
        body = f"""
{alert_type.upper()}
{'=' * 50}

Location: {location_name}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Alert Details:
{conditions_list}

This is an automated alert from Weather Monitor.
Please take appropriate action based on the alert type.
        """

        msg.attach(MIMEText(body, 'plain'))

        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        logger.info(f"{alert_type} sent for {location_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


def send_test_alert(sender_email, sender_password, recipient_emails):
    """Send a test alert email"""
    try:
        # Create email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = "✅ Weather Monitor - Test Alert"

        # Email body
        body = f"""
WEATHER MONITOR TEST
====================

This is a test email from the Weather Monitor system.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

✅ Email system is working correctly!
Your weather alerts are configured and ready to receive notifications.

Features:
  • Monitors US locations for NWS critical alerts (Warnings, Watches)
  • Alert types monitored: Tornado, Flood, Severe Thunderstorm, Winter Storm, Extreme Cold/Heat, Hurricane, High Wind, Red Flag, and more
  • Sends alerts immediately when warnings/watches are issued
  • Deduplication prevents repeated alerts for the same advisory

This is an automated message.
        """

        msg.attach(MIMEText(body, 'plain'))

        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        logger.info(f"Test alert sent successfully to {', '.join(recipient_emails)}")
        return True

    except Exception as e:
        logger.error(f"Failed to send test email alert: {e}")
        return False


def main():
    """Main weather monitoring loop"""
    logger.info("Starting weather alert check for multiple locations...")

    # Load configuration
    config = load_config()

    # Validate required fields
    if not config.get('openweathermap_api_key'):
        logger.error("OPENWEATHERMAP_API_KEY not set")
        return

    if not config.get('sender_email') or not config.get('sender_password'):
        logger.error("Email credentials not set")
        return

    recipient_emails = [e.strip() for e in config.get('recipient_emails', []) if e.strip()]
    if not recipient_emails:
        logger.error("No recipient emails configured")
        return

    # Create an NWS session with proper headers (User-Agent + Accept)
    nws_contact = config.get('nws_contact') or os.getenv('NWS_CONTACT')
    nws_session = make_nws_session(nws_contact)

    # Check if TEST_MODE is enabled
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'

    if test_mode:
        logger.info("🧪 TEST MODE ENABLED - Sending test alert...")
        send_test_alert(
            config['sender_email'],
            config['sender_password'],
            recipient_emails
        )
        logger.info("✅ Test alert sent! Check your inbox.")
        return

    locations = config.get('locations', [])
    if not locations:
        logger.error("No locations configured")
        return

    # Load previously sent alerts
    sent_alerts = load_sent_alerts()

    # Check weather for each location
    alerts_sent = 0
    for location in locations:
        location_name = location.get('name', 'Unknown')
        lat = location.get('lat')
        lon = location.get('lon')
        country = location.get('country', 'XX')

        if lat is None or lon is None:
            logger.warning(f"Invalid coordinates for {location_name}")
            continue

        logger.info(f"Checking alerts for {location_name} ({country})...")

        # Check if this is a US location - use NWS alerts
        if country.upper() == 'US':
            logger.info(f"Fetching National Weather Service alerts for {location_name}...")
            nws_features = get_nws_alerts(lat, lon, location_name, session=nws_session)

            if nws_features:
                nws_alerts = parse_nws_alerts(nws_features)

                if nws_alerts:
                    # Create unique alert keys for each alert
                    for alert_text in nws_alerts:
                        # Extract event type from alert text (first line)
                        event_type = alert_text.split('\n')[0].split('(')[0].strip()
                        # Use event type + location + timestamp for uniqueness
                        alert_key = f"{location_name}_{event_type}_{datetime.now().strftime('%Y-%m-%d-%H:%M')}"

                        if alert_key not in sent_alerts:
                            if send_alert_email(
                                config['sender_email'],
                                config['sender_password'],
                                recipient_emails,
                                location_name,
                                [alert_text],
                                alert_type=event_type
                            ):
                                sent_alerts[alert_key] = datetime.now().isoformat()
                                alerts_sent += 1
                        else:
                            logger.debug(f"Alert already processed: {alert_key}")
                else:
                    logger.info(f"No critical alerts for {location_name}")
            else:
                logger.info(f"No alerts returned from NWS for {location_name}")
        else:
            logger.debug(f"Skipping {location_name} - only US locations use NWS alerts")

    # Save sent alerts
    save_sent_alerts(sent_alerts)

    logger.info(f"Alert check complete. Critical alerts sent: {alerts_sent}")


if __name__ == '__main__':
    main()
