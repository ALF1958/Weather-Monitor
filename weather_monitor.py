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
import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

# Additional keywords for significant alerts across providers (case-insensitive)
SIGNIFICANT_ALERT_KEYWORDS = {
    'tornado',
    'flood',
    'flash flood',
    'severe thunderstorm',
    'hurricane',
    'tropical storm',
    'winter storm',
    'blizzard',
    'ice storm',
    'high wind',
    'extreme cold',
    'extreme heat',
    'heat advisory',
    'red flag',
    'fire weather',
    'avalanche',
    'air quality',
    'lightning',
    'hail',
}

SIGNIFICANT_ALERT_PATTERNS = [
    re.compile(
        rf"\b{re.escape(keyword).replace(' ', r'[\s-]*')}\b",
        re.IGNORECASE
    )
    for keyword in SIGNIFICANT_ALERT_KEYWORDS
]

# Track sent alerts to avoid duplicates
SENT_ALERTS_FILE = 'sent_alerts.json'

# Persistent cache file for NWS /points -> alerts URL (reduces calls across runs)
NWS_POINTS_CACHE_FILE = 'nws_points_cache.json'
# Default TTL for cached points (hours)
NWS_CACHE_TTL_HOURS = int(os.getenv('NWS_CACHE_TTL_HOURS', '24'))

# In-memory cache for runtime as well
NWS_POINTS_CACHE = {}


def make_stable_alert_id(*parts):
    """Create a stable alert identifier from provider-specific stable fields."""
    normalized = json.dumps([str(part or '').strip() for part in parts], ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def normalize_country(country_value):
    """Normalize country value for comparison."""
    return (country_value or 'UNSPECIFIED').upper()


def timestamp_to_utc_iso(timestamp):
    """Convert epoch timestamp to UTC ISO string safely."""
    if not isinstance(timestamp, (int, float)):
        return 'Unknown'
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return 'Unknown'


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


def load_nws_points_cache():
    """Load persistent NWS points cache from disk into NWS_POINTS_CACHE (in-memory)."""
    global NWS_POINTS_CACHE
    if os.path.exists(NWS_POINTS_CACHE_FILE):
        try:
            with open(NWS_POINTS_CACHE_FILE, 'r') as f:
                data = json.load(f)
                NWS_POINTS_CACHE = data
        except Exception as e:
            logger.warning(f"Could not load NWS points cache: {e}")
            NWS_POINTS_CACHE = {}
    else:
        NWS_POINTS_CACHE = {}


def save_nws_points_cache():
    """Persist the in-memory NWS_POINTS_CACHE to disk."""
    try:
        with open(NWS_POINTS_CACHE_FILE, 'w') as f:
            json.dump(NWS_POINTS_CACHE, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save NWS points cache: {e}")


def is_cache_entry_valid(entry):
    """Return True if a cache entry is still valid according to TTL."""
    try:
        cached_at = entry.get('cached_at')
        if not cached_at:
            return False
        ts = datetime.fromisoformat(cached_at)
        if datetime.utcnow() - ts <= timedelta(hours=NWS_CACHE_TTL_HOURS):
            return True
        return False
    except Exception:
        return False


def make_nws_session(contact=None):
    """Create and return a requests.Session configured for NWS API usage.

    NWS (api.weather.gov) does NOT require an API key, but requests that callers
    send a descriptive User-Agent including a contact email or URL. Provide this
    via the NWS_CONTACT env var or the config (nws_contact). If no contact is
    provided, a generic contact token is used, but it's recommended to set a
    real email or URL.

    This session also installs a Retry/HTTPAdapter to provide basic retry and
    backoff (handles transient errors and HTTP 429/5xx responses).
    """
    sess = requests.Session()
    contact_val = contact or os.getenv('NWS_CONTACT') or 'ALF1958'
    user_agent = f"Weather Monitor/1.0 ({contact_val})"

    headers = {
        'User-Agent': user_agent,
        'Accept': 'application/geo+json',
    }
    sess.headers.update(headers)

    # Configure retries: handle 429 and common server errors with backoff
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    sess.mount('https://', adapter)
    sess.mount('http://', adapter)

    return sess


def make_owm_session():
    """Create and return a requests.Session configured for OpenWeatherMap usage."""
    sess = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    sess.mount('https://', adapter)
    sess.mount('http://', adapter)

    return sess


def get_nws_alerts(lat, lon, location_name, session=None):
    """Fetch alerts from National Weather Service (US only).

    Uses a requests.Session with appropriate User-Agent and Accept headers.
    Caches the points -> alerts URL mapping on-disk to reduce calls to /points
    across runs. The persistent cache respects a TTL (default 24 hours) and is
    configurable via NWS_CACHE_TTL_HOURS env var.
    """
    sess = session or make_nws_session()
    cache_key = f"{lat},{lon}"

    try:
        # Load persistent cache into memory once
        if not NWS_POINTS_CACHE:
            load_nws_points_cache()

        alerts_url = None
        entry = NWS_POINTS_CACHE.get(cache_key)
        if entry and is_cache_entry_valid(entry):
            alerts_url = entry.get('alerts_url')
            logger.debug(f"Using cached alerts URL for {location_name}")

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

            # Cache the alerts URL with timestamp
            NWS_POINTS_CACHE[cache_key] = {
                'alerts_url': alerts_url,
                'cached_at': datetime.utcnow().isoformat()
            }
            # Persist updated cache
            save_nws_points_cache()

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


def get_openweathermap_alerts(lat, lon, location_name, api_key, session=None):
    """Fetch alerts from OpenWeatherMap One Call API (global coverage)."""
    sess = session or make_owm_session()

    try:
        endpoint = "https://api.openweathermap.org/data/3.0/onecall"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': api_key,
        }

        response = sess.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        alerts = data.get('alerts', [])
        if alerts:
            logger.info(f"Found {len(alerts)} OpenWeatherMap alerts for {location_name}")
            return alerts
        return None

    except requests.exceptions.RequestException as e:
        logger.warning(f"Error fetching OpenWeatherMap alerts for {location_name}: {e}")
        return None


def is_significant_alert(event, headline='', description='', tags=None):
    """Return True when an alert matches significant event types or keywords."""
    if event in CRITICAL_ALERT_TYPES:
        return True

    tags = tags or []
    combined_text = f"{event or ''} {headline or ''} {description or ''} {' '.join(tags)}"
    return any(pattern.search(combined_text) for pattern in SIGNIFICANT_ALERT_PATTERNS)


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

        description = props.get('description', '')

        # Include significant alert types
        if is_significant_alert(event, headline=headline, description=description):
            alert_text = f"{event} ({severity})"
            if headline:
                alert_text += f"\n{headline}"
            if effective or expires:
                alert_text += f"\nEffective: {effective} | Expires: {expires}"
            alert_id = feature.get('id') or props.get('id') or make_stable_alert_id(event, props.get('areaDesc', ''), headline, effective)

            alerts.append({
                'id': alert_id,
                'event': event,
                'text': alert_text,
            })
            logger.info(f"Significant alert identified: {event} for {props.get('areaDesc', 'Unknown area')}")
        else:
            logger.debug(f"Non-significant alert filtered out: {event}")

    return alerts if alerts else None


def parse_openweathermap_alerts(raw_alerts):
    """Parse OpenWeatherMap alert payload into significant alerts only."""
    alerts = []

    for raw_alert in raw_alerts:
        event = raw_alert.get('event', 'Weather Alert')
        sender = raw_alert.get('sender_name', 'Unknown sender')
        description = raw_alert.get('description', '')
        start_ts = raw_alert.get('start')
        end_ts = raw_alert.get('end')
        tags = raw_alert.get('tags', [])

        if not is_significant_alert(event, description=description, tags=tags):
            logger.debug(f"OpenWeatherMap non-significant alert filtered out: {event}")
            continue

        start_text = timestamp_to_utc_iso(start_ts)
        end_text = timestamp_to_utc_iso(end_ts)
        alert_text = f"{event}\nSource: {sender}\nEffective: {start_text} | Expires: {end_text}"
        if description:
            alert_text += f"\n{description}"

        alert_id = make_stable_alert_id(event, sender, start_ts)

        alerts.append({
            'id': alert_id,
            'event': event,
            'text': alert_text,
        })
        logger.info(f"Significant OpenWeatherMap alert identified: {event}")

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
    if not config.get('sender_email') or not config.get('sender_password'):
        logger.error("Email credentials not set")
        return

    recipient_emails = [e.strip() for e in config.get('recipient_emails', []) if e.strip()]
    if not recipient_emails:
        logger.error("No recipient emails configured")
        return

    locations = config.get('locations', [])
    if not locations:
        logger.error("No locations configured")
        return

    has_non_us_locations = any(normalize_country(loc.get('country')) != 'US' for loc in locations)
    openweathermap_api_key = config.get('openweathermap_api_key')
    if has_non_us_locations and not openweathermap_api_key:
        logger.error("OPENWEATHERMAP_API_KEY not set (required for non-US locations)")
        return

    # Create an NWS session with proper headers (User-Agent + Accept)
    nws_contact = config.get('nws_contact') or os.getenv('NWS_CONTACT')
    nws_session = make_nws_session(nws_contact)
    owm_session = make_owm_session()

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

    # Load previously sent alerts
    sent_alerts = load_sent_alerts()

    # Check weather for each location
    alerts_sent = 0
    for location in locations:
        location_name = location.get('name', 'Unknown')
        lat = location.get('lat')
        lon = location.get('lon')
        country = normalize_country(location.get('country'))

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
                    # Create stable alert keys for each provider alert
                    for alert in nws_alerts:
                        alert_key = f"NWS::{location_name}::{alert['id']}"

                        if alert_key not in sent_alerts:
                            if send_alert_email(
                                config['sender_email'],
                                config['sender_password'],
                                recipient_emails,
                                location_name,
                                [alert['text']],
                                alert_type=alert['event']
                            ):
                                sent_alerts[alert_key] = datetime.now().isoformat()
                                alerts_sent += 1
                        else:
                            logger.debug(f"Alert already processed: {alert_key}")
                else:
                    logger.info(f"No significant alerts for {location_name}")
            else:
                logger.info(f"No alerts returned from NWS for {location_name}")
        else:
            logger.info(f"Fetching OpenWeatherMap alerts for {location_name}...")
            owm_raw_alerts = get_openweathermap_alerts(
                lat,
                lon,
                location_name,
                openweathermap_api_key,
                session=owm_session
            )

            if owm_raw_alerts:
                owm_alerts = parse_openweathermap_alerts(owm_raw_alerts)
                if owm_alerts:
                    for alert in owm_alerts:
                        alert_key = f"OWM::{location_name}::{alert['id']}"
                        if alert_key not in sent_alerts:
                            if send_alert_email(
                                config['sender_email'],
                                config['sender_password'],
                                recipient_emails,
                                location_name,
                                [alert['text']],
                                alert_type=alert['event']
                            ):
                                sent_alerts[alert_key] = datetime.now().isoformat()
                                alerts_sent += 1
                        else:
                            logger.debug(f"Alert already processed: {alert_key}")
                else:
                    logger.info(f"No significant alerts for {location_name}")
            else:
                logger.info(f"No alerts returned from OpenWeatherMap for {location_name}")

    # Save sent alerts
    save_sent_alerts(sent_alerts)

    logger.info(f"Alert check complete. Significant alerts sent: {alerts_sent}")


if __name__ == '__main__':
    main()
