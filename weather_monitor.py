#!/usr/bin/env python3
"""
Weather Monitor - Alerts for Severe Weather & Advisories
Monitors multiple locations and sends email alerts for severe weather conditions and official advisories
Uses National Weather Service (NWS) for US locations and OpenWeatherMap for international locations
"""

import os
import json
import hashlib
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.mime.application import MIMEApplication
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
CRITICAL_ALERT_KEYWORDS = tuple(alert_type.lower() for alert_type in CRITICAL_ALERT_TYPES)

# Track sent alerts to avoid duplicates
SENT_ALERTS_FILE = 'sent_alerts.json'

# Persistent cache file for legacy NWS /points -> alerts URL fallback data
NWS_POINTS_CACHE_FILE = 'nws_points_cache.json'
# Default TTL for cached points (hours)
NWS_CACHE_TTL_HOURS = int(os.getenv('NWS_CACHE_TTL_HOURS', '24'))

# In-memory cache for runtime as well
NWS_POINTS_CACHE = {}
MONITOR_STATE_FILE = 'monitor_state.json'

# --- Dashboard output file (configurable via env var) ---
DASHBOARD_DIGEST_FILE = os.getenv('DASHBOARD_DIGEST_FILE', 'dashboard_digest.json')

# Priority score band thresholds (configurable via env vars; default values match scoring model)
PRIORITY_CRITICAL_MIN = int(os.getenv('PRIORITY_CRITICAL_MIN', '85'))
PRIORITY_HIGH_MIN = int(os.getenv('PRIORITY_HIGH_MIN', '65'))
PRIORITY_MEDIUM_MIN = int(os.getenv('PRIORITY_MEDIUM_MIN', '40'))

# Scoring weight knobs — all numeric, all overridable via env vars
_W_SEVERITY = {
    'extreme':  int(os.getenv('WEIGHT_SEVERITY_EXTREME',  '50')),
    'severe':   int(os.getenv('WEIGHT_SEVERITY_SEVERE',   '35')),
    'moderate': int(os.getenv('WEIGHT_SEVERITY_MODERATE', '20')),
    'minor':    int(os.getenv('WEIGHT_SEVERITY_MINOR',    '10')),
    'unknown':  0,
}
# Per-event-type bonus applied once per matching alert (first match wins)
_W_EVENT_BONUS = {
    'tornado warning':             int(os.getenv('WEIGHT_EVENT_TORNADO_WARNING',     '35')),
    'hurricane warning':           int(os.getenv('WEIGHT_EVENT_HURRICANE_WARNING',   '35')),
    'flash flood warning':         int(os.getenv('WEIGHT_EVENT_FLASH_FLOOD_WARNING', '28')),
    'severe thunderstorm warning': int(os.getenv('WEIGHT_EVENT_TSTORM_WARNING',      '24')),
    'blizzard warning':            int(os.getenv('WEIGHT_EVENT_BLIZZARD_WARNING',    '24')),
    'red flag warning':            int(os.getenv('WEIGHT_EVENT_RED_FLAG_WARNING',    '20')),
}
_W_ESCALATION_BONUS = int(os.getenv('WEIGHT_ESCALATION_BONUS', '18'))
_W_RISK_CAT_BONUS   = int(os.getenv('WEIGHT_RISK_CAT_BONUS',   '8'))
_W_RISK_CAT_MAX     = int(os.getenv('WEIGHT_RISK_CAT_MAX',     '24'))

SEVERITY_RANK = {
    'unknown': 0,
    'minor': 1,
    'moderate': 2,
    'severe': 3,
    'extreme': 4,
}

FORECAST_RISK_KEYWORDS = {
    'Severe Thunderstorms': (
        'severe thunderstorm',
        'damaging wind',
        'large hail',
        'tornado',
        'strong thunderstorm',
    ),
    'Flooding': (
        'flash flood',
        'flooding',
        'flood',
        'excessive rainfall',
        'heavy rain',
    ),
    'Winter Weather': (
        'winter storm',
        'blizzard',
        'snow',
        'ice',
        'freezing rain',
        'sleet',
        'wind chill',
    ),
    'Extreme Heat/Cold': (
        'heat index',
        'dangerous heat',
        'extreme heat',
        'record heat',
        'extreme cold',
        'dangerous cold',
        'hard freeze',
    ),
    'High Wind': (
        'high wind',
        'wind advisory',
        'strong winds',
        'gust',
    ),
    'Fire Weather': (
        'red flag',
        'fire weather',
        'critical fire',
        'dry and windy',
    ),
    'Poor Air Quality': (
        'air quality',
        'smoke',
        'ozone',
        'unhealthy air',
    ),
}

HAZARD_CATEGORY_ALIASES = {
    'severe thunderstorms': 'Severe Thunderstorms',
    'severe thunderstorm': 'Severe Thunderstorms',
    'thunderstorms': 'Severe Thunderstorms',
    'thunderstorm': 'Severe Thunderstorms',
    'storms': 'Severe Thunderstorms',
    'storm': 'Severe Thunderstorms',
    'tornado': 'Severe Thunderstorms',
    'hurricane': 'Severe Thunderstorms',
    'tropical storm': 'Severe Thunderstorms',
    'flooding': 'Flooding',
    'flood': 'Flooding',
    'winter weather': 'Winter Weather',
    'winter': 'Winter Weather',
    'snow': 'Winter Weather',
    'ice': 'Winter Weather',
    'heat': 'Extreme Heat/Cold',
    'extreme heat': 'Extreme Heat/Cold',
    'cold': 'Extreme Heat/Cold',
    'extreme cold': 'Extreme Heat/Cold',
    'freeze': 'Extreme Heat/Cold',
    'high wind': 'High Wind',
    'wind': 'High Wind',
    'fire weather': 'Fire Weather',
    'fire': 'Fire Weather',
    'air quality': 'Poor Air Quality',
    'air': 'Poor Air Quality',
    'smoke': 'Poor Air Quality',
}

ALERT_HAZARD_KEYWORDS = {
    'Severe Thunderstorms': (
        'tornado',
        'severe thunderstorm',
        'thunderstorm',
        'hurricane',
        'tropical storm',
        'hail',
        'lightning',
    ),
    'Flooding': (
        'flood',
    ),
    'Winter Weather': (
        'winter',
        'blizzard',
        'snow',
        'ice',
        'freezing rain',
        'sleet',
        'wind chill',
        'avalanche',
    ),
    'Extreme Heat/Cold': (
        'heat',
        'cold',
        'freeze',
        'frost',
    ),
    'High Wind': (
        'wind',
        'gust',
    ),
    'Fire Weather': (
        'red flag',
        'fire weather',
        'fire',
    ),
    'Poor Air Quality': (
        'air quality',
        'smoke',
        'ozone',
    ),
}


def canonicalize_hazard_category(name):
    """Return the canonical hazard category name used by the scoring system."""
    if not name:
        return None
    normalized = ' '.join(str(name).strip().lower().split())
    if not normalized:
        return None
    for category in FORECAST_RISK_KEYWORDS:
        if normalized == category.lower():
            return category
    return HAZARD_CATEGORY_ALIASES.get(normalized)


def _read_numeric_weight(value, default=1.0, minimum=0.0):
    """Parse a numeric weight and clamp invalid values back to a safe default."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return default
    return parsed


def get_location_priority_profile(location):
    """Extract location-specific weighting and operational context from config."""
    priority_weight = _read_numeric_weight(
        location.get('priority_weight', location.get('weight', 1.0)),
        default=1.0,
        minimum=0.0,
    )

    raw_hazard_weights = location.get('hazard_weights') or location.get('risk_weights') or {}
    hazard_weights = {}
    if isinstance(raw_hazard_weights, dict):
        for raw_name, raw_weight in raw_hazard_weights.items():
            canonical_name = canonicalize_hazard_category(raw_name)
            if not canonical_name:
                logger.warning(
                    f"Ignoring unknown hazard weight '{raw_name}' for "
                    f"{location.get('name', 'Unknown')}"
                )
                continue
            hazard_weights[canonical_name] = _read_numeric_weight(
                raw_weight,
                default=1.0,
                minimum=0.0,
            )

    raw_vulnerabilities = location.get('operational_vulnerabilities', [])
    if isinstance(raw_vulnerabilities, str):
        operational_vulnerabilities = [raw_vulnerabilities.strip()] if raw_vulnerabilities.strip() else []
    elif isinstance(raw_vulnerabilities, list):
        operational_vulnerabilities = [
            str(item).strip() for item in raw_vulnerabilities if str(item).strip()
        ]
    else:
        operational_vulnerabilities = []

    leadership_note = str(location.get('leadership_note', '') or '').strip()

    return {
        'priority_weight': priority_weight,
        'hazard_weights': hazard_weights,
        'operational_vulnerabilities': operational_vulnerabilities,
        'leadership_note': leadership_note,
    }


def classify_alert_hazard(event_type):
    """Map an alert event name to a configured hazard category when possible."""
    normalized = (event_type or '').strip().lower()
    if not normalized:
        return None
    for category, keywords in ALERT_HAZARD_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return None


def get_hazard_weight_multiplier(hazard_weights, category_name):
    """Return the configured multiplier for one hazard category."""
    canonical_name = canonicalize_hazard_category(category_name)
    if not canonical_name:
        return 1.0
    return _read_numeric_weight((hazard_weights or {}).get(canonical_name, 1.0), default=1.0, minimum=0.0)


def build_priority_reasons(
    active_alerts,
    risk_summary,
    is_escalating,
    hazard_weights=None,
    operational_vulnerabilities=None,
    leadership_note='',
):
    """Build plain-language reasons that explain why a location ranked as it did."""
    reasons = []
    hazard_weights = hazard_weights or {}
    operational_vulnerabilities = operational_vulnerabilities or []

    if is_escalating:
        reasons.append("Conditions are worsening compared with the previous run.")

    if active_alerts:
        top_events = ', '.join(
            alert.get('event_type', 'Alert')
            for alert in active_alerts[:2]
            if alert.get('event_type')
        )
        if top_events:
            reasons.append(f"Active alerts in effect: {top_events}.")

    if risk_summary.get('has_elevated_risk'):
        reasons.append(
            "Forecast risks identified: "
            + ', '.join(risk_summary.get('top_categories', []))
            + "."
        )

    amplified_categories = []
    for category in risk_summary.get('top_categories', []):
        weight = get_hazard_weight_multiplier(hazard_weights, category)
        if weight > 1:
            amplified_categories.append(f"{category} (x{weight:g})")

    for alert in active_alerts:
        category = classify_alert_hazard(alert.get('event_type', ''))
        weight = get_hazard_weight_multiplier(hazard_weights, category)
        if category and weight > 1:
            amplified_label = f"{category} (x{weight:g})"
            if amplified_label not in amplified_categories:
                amplified_categories.append(amplified_label)

    if amplified_categories:
        amplified_text = ', '.join(amplified_categories)
        if operational_vulnerabilities:
            reasons.append(
                f"Location-specific weighting boosts {amplified_text} because of: "
                + '; '.join(operational_vulnerabilities)
                + "."
            )
        else:
            reasons.append(f"Location-specific weighting boosts {amplified_text}.")
    elif operational_vulnerabilities:
        reasons.append(
            "Operational concerns noted for this location: "
            + '; '.join(operational_vulnerabilities)
            + "."
        )

    if leadership_note:
        reasons.append(leadership_note)

    return reasons


def load_config():
    """Load configuration from a config file and environment variables.

    Loading priority (highest to lowest):
      1. Environment variables for credentials — these always win over the file.
         This allows a committed config file to carry the site list while
         secrets come safely from GitHub Secrets / environment variables.
      2. Config file values (CONFIG_PATH env var, or config.json by default).
      3. Built-in default site list when no locations are provided by any source.
    """
    config_path = os.getenv('CONFIG_PATH', 'config.json')

    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.warning(f"Could not load {config_path}: {e}")

    # Environment variables always override file values for credentials.
    # Empty/unset env vars do not overwrite a value already in the file.
    for env_key, config_key in (
        ('OPENWEATHERMAP_API_KEY', 'openweathermap_api_key'),
        ('SENDER_EMAIL',          'sender_email'),
        ('SENDER_PASSWORD',       'sender_password'),
        ('NWS_CONTACT',           'nws_contact'),
    ):
        val = os.getenv(env_key)
        if val:
            config[config_key] = val

    # RECIPIENT_EMAILS arrives as a comma-separated string when set via env var.
    recipient_env = os.getenv('RECIPIENT_EMAILS')
    if recipient_env:
        config['recipient_emails'] = [e.strip() for e in recipient_env.split(',') if e.strip()]

    # Use built-in default location list only when no locations were provided.
    if not config.get('locations'):
        config['locations'] = [
            {'name': 'TSC HAWAII', 'lat': 21.483, 'lon': -158.0827, 'country': 'US'},
            {'name': 'TSC CORPUS CHRISTI', 'lat': 27.6905, 'lon': -97.2894, 'country': 'US'},
            {'name': 'TSC FT POLK', 'lat': 31.033, 'lon': -93.183, 'country': 'US'},
            {'name': 'TSC FT HOOD', 'lat': 31.133, 'lon': -97.7663, 'country': 'US'},
            {'name': 'TSC FT RUCKER', 'lat': 31.3166, 'lon': -85.7333, 'country': 'US'},
            {'name': 'TSC FT HUACHUCA', 'lat': 31.55, 'lon': -110.3327, 'country': 'US'},
            {'name': 'TSC FT BLISS', 'lat': 31.8, 'lon': -106.4158, 'country': 'US'},
            {'name': 'TSC HUNTER AAF', 'lat': 32.01, 'lon': -81.1461, 'country': 'US'},
            {'name': 'TSC FT BENNING', 'lat': 32.383, 'lon': -84.883, 'country': 'US'},
            {'name': 'TSC WHITE SANDS', 'lat': 32.4, 'lon': -106.4, 'country': 'US'},
            {'name': 'TSC YUMA', 'lat': 32.6538, 'lon': -114.6058, 'country': 'US'},
            {'name': 'TSC FT GORDON', 'lat': 33.4163, 'lon': -82.133, 'country': 'US'},
            {'name': 'TSC RED RIVER', 'lat': 33.4166, 'lon': -94.2663, 'country': 'US'},
            {'name': 'TSC ANNISTON', 'lat': 33.633, 'lon': -85.8663, 'country': 'US'},
            {'name': 'TSC REDSTONE ARSENAL', 'lat': 34.6166, 'lon': -86.6666, 'country': 'US'},
            {'name': 'TSC FT SILL', 'lat': 34.65, 'lon': -98.4, 'country': 'US'},
            {'name': 'TSC MCALESTER', 'lat': 34.833, 'lon': -95.925, 'country': 'US'},
            {'name': 'TSC FT BRAGG', 'lat': 35.133, 'lon': -78.983, 'country': 'US'},
            {'name': 'TSC FT IRWIN', 'lat': 35.383, 'lon': -116.5827, 'country': 'US'},
            {'name': 'TSC JAPAN', 'lat': 35.583, 'lon': 139.4163, 'country': 'JP'},
            {'name': 'TSC CARROLL', 'lat': 36, 'lon': 128.4166, 'country': 'KR'},
            {'name': 'TSC FT CAMPBELL', 'lat': 36.6663, 'lon': -87.483, 'country': 'US'},
            {'name': 'TSC CP HUMPHRIES', 'lat': 36.9166, 'lon': 127.05, 'country': 'KR'},
            {'name': 'TSC FT EUSTIS', 'lat': 37.15, 'lon': -76.583, 'country': 'US'},
            {'name': 'TSC FT LEONARD WOOD', 'lat': 37.733, 'lon': -92.1163, 'country': 'US'},
            {'name': 'TSC FT KNOX', 'lat': 37.9, 'lon': -85.9833, 'country': 'US'},
            {'name': 'TSC SACRAMENTO', 'lat': 38.4891, 'lon': -121.395, 'country': 'US'},
            {'name': 'TSC FT CARSON', 'lat': 38.683, 'lon': -104.7658, 'country': 'US'},
            {'name': 'TSC FT MEADE', 'lat': 39.1, 'lon': -76.7163, 'country': 'US'},
            {'name': 'TSC FT RILEY', 'lat': 39.1663, 'lon': -96.8163, 'country': 'US'},
            {'name': 'TSC ABERDEEN', 'lat': 39.4913, 'lon': -76.1358, 'country': 'US'},
            {'name': 'TSC LETTERKENNY', 'lat': 39.983, 'lon': -77.65, 'country': 'US'},
            {'name': 'TSC FT DIX', 'lat': 40.0166, 'lon': -74.8666, 'country': 'US'},
            {'name': 'TSC DUGWAY', 'lat': 40.183, 'lon': -112.9327, 'country': 'US'},
            {'name': 'TSC TOBYHANNA', 'lat': 41.183, 'lon': -75.4163, 'country': 'US'},
            {'name': 'TSC ROCK ISLAND', 'lat': 41.5352, 'lon': -90.5686, 'country': 'US'},
            {'name': 'TSC WARREN', 'lat': 42.5, 'lon': -83.4, 'country': 'US'},
            {'name': 'TSC FT DRUM', 'lat': 44.05, 'lon': -75.733, 'country': 'US'},
            {'name': 'TSC JBLM FT LEWIS', 'lat': 47.083, 'lon': -122.6, 'country': 'US'},
            {'name': 'LAB NUCLEAR REF', 'lat': 49.2, 'lon': 7.6, 'country': 'DE'},
            {'name': 'TSC KAISERSLAUTERN', 'lat': 49.4475, 'lon': 7.8391, 'country': 'DE'},
            {'name': 'TSC ILLESHEIM', 'lat': 49.4805, 'lon': 10.3861, 'country': 'DE'},
            {'name': 'TSC VILSECK', 'lat': 49.6286, 'lon': 11.785, 'country': 'DE'},
            {'name': 'TSC WIESBADEN', 'lat': 49.9691, 'lon': 8.1186, 'country': 'DE'},
            {'name': 'TSC WAINWRIGHT', 'lat': 64.833, 'lon': -147.5827, 'country': 'US'},
        ]

    return config


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


def load_monitor_state():
    """Load persistent monitor state (digest + escalation fingerprints)."""
    if os.path.exists(MONITOR_STATE_FILE):
        try:
            with open(MONITOR_STATE_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Could not load monitor state: {e}")
    return {}


def save_monitor_state(state):
    """Persist monitor state to disk."""
    try:
        with open(MONITOR_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save monitor state: {e}")


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
        # Older cache files stored UTC timestamps without timezone info.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if datetime.now(UTC) - ts <= timedelta(hours=NWS_CACHE_TTL_HOURS):
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


def parse_iso_datetime(value):
    """Parse an ISO timestamp and return timezone-aware UTC datetime."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)
    except Exception:
        return None


def read_bool_setting(config, key, default):
    """Read bool config with env override support."""
    env_key = key.upper()
    raw_value = os.getenv(env_key)
    if raw_value is None:
        raw_value = config.get(key, default)

    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(raw_value)


def read_int_setting(config, key, default):
    """Read integer config with env override support."""
    env_key = key.upper()
    raw_value = os.getenv(env_key)
    if raw_value is None:
        raw_value = config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return value


def fetch_nws_alert_features(session, alerts_url, location_name):
    """Fetch and return raw NWS alert features from a specific NWS alerts URL.

    In the NWS API, "features" are the individual alert objects in the response.
    Returns a list of alert features when alerts are present, or None when the
    response contains no active alerts for the location.
    """
    response = session.get(alerts_url, timeout=10)
    response.raise_for_status()
    alerts_data = response.json()

    features = alerts_data.get('features', [])
    if features:
        logger.info(f"Found {len(features)} alerts for {location_name}")
        return features

    return None


def get_zone_id_from_url(zone_url):
    """Extract an NWS zone ID from a zone URL.

    NWS zones are geographic areas used by the National Weather Service
    to group and publish weather alerts.

    Parameters:
        zone_url: Full NWS zone URL string (for example,
            "https://api.weather.gov/zones/forecast/KYZ007").

    Returns:
        Zone ID string (for example, KYZ007), or None when unavailable.
    """
    if not zone_url:
        return None
    return zone_url.rstrip('/').split('/')[-1]


def get_nws_point_metadata(lat, lon, cache_key, location_name, session):
    """Return /points metadata needed for broader NWS alert matching.

    Includes:
      - forecast zone ID
      - county zone ID
      - legacy alerts URL

    Parameters:
        lat: Latitude for the location.
        lon: Longitude for the location.
        cache_key: Cache key in "lat,lon" format.
        location_name: Human-friendly location name for logging.
        session: Requests session used for API calls.

    Returns:
        Dictionary with cached_at, zone_ids, and alerts_url keys.
    """
    entry = NWS_POINTS_CACHE.get(cache_key)
    if entry and is_cache_entry_valid(entry):
        if entry.get('zone_ids') or entry.get('alerts_url'):
            logger.debug(f"Using cached NWS points metadata for {location_name}")
            return entry

    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    response = session.get(points_url, timeout=10)
    response.raise_for_status()
    points_data = response.json()
    props = points_data.get('properties', {})

    forecast_zone_id = get_zone_id_from_url(props.get('forecastZone'))
    county_zone_id = get_zone_id_from_url(props.get('county'))
    zone_ids = []
    # Forecast zone and county zone can occasionally be the same ID.
    # Keep only unique IDs so we do not query the same zone twice.
    if forecast_zone_id:
        zone_ids.append(forecast_zone_id)
    if county_zone_id and county_zone_id != forecast_zone_id:
        zone_ids.append(county_zone_id)

    metadata = {
        'zone_ids': zone_ids,
        'alerts_url': props.get('alerts'),
        'forecast_url': props.get('forecast'),
        'forecast_hourly_url': props.get('forecastHourly'),
        'cached_at': datetime.now(UTC).isoformat()
    }
    NWS_POINTS_CACHE[cache_key] = metadata
    save_nws_points_cache()
    return metadata


def merge_alert_features(feature_groups):
    """Merge alert feature lists while removing duplicates.

    In NWS API responses, each "feature" is one alert record.

    Parameters:
        feature_groups: List of feature lists to merge.

    Returns:
        Merged feature list with duplicates removed, or None when empty.
    """
    merged = []
    seen_keys = set()

    for features in feature_groups:
        if not features:
            continue
        for feature in features:
            feature_id = feature.get('id')
            if feature_id:
                dedupe_key = feature_id
            else:
                props = feature.get('properties', {})
                # Older or incomplete NWS alert records may omit a stable
                # top-level "id". In that case, use event + headline + timing
                # fields as a best-effort identity key to avoid duplicate
                # notifications. Without this check, users may receive repeat
                # emails for the same alert.
                # This tuple (a grouped set of values) acts like a backup ID.
                dedupe_key = (
                    props.get('event', ''),
                    props.get('headline', ''),
                    props.get('effective', ''),
                    props.get('expires', ''),
                )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            merged.append(feature)

    return merged if merged else None


def get_nws_alerts_by_zone(zone_ids, location_name, session):
    """Fetch alerts by NWS zone IDs and return merged features.

    When multiple zone IDs are provided, this function queries each zone
    separately and combines the results.

    Parameters:
        zone_ids: List of NWS zone IDs, such as ["KYZ007", "KYC047"].
        location_name: Human-friendly location name for logging.
        session: Requests session used for API calls.

    Returns:
        Merged alert features list, or None when no alerts are found.
    """
    if not zone_ids:
        return None

    zone_features = []
    for zone_id in zone_ids:
        alerts_url = f"https://api.weather.gov/alerts/active?zone={zone_id}"
        try:
            features = fetch_nws_alert_features(session, alerts_url, location_name)
            if features:
                logger.info(f"Found alerts for {location_name} in weather zone {zone_id}")
                zone_features.append(features)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Zone-based NWS alert lookup failed for {location_name} ({zone_id}): {e}")

    return merge_alert_features(zone_features)


def get_nws_alerts(lat, lon, location_name, session=None):
    """Fetch alerts from National Weather Service (US only).

    Uses a requests.Session with appropriate User-Agent and Accept headers.
    First queries NWS by zone/county granularity using /points metadata, then
    performs a point-based lookup as a secondary check. If both methods return
    data, features are merged and deduplicated. The /points metadata is cached
    with a TTL (default 24 hours) configurable via NWS_CACHE_TTL_HOURS.
    """
    sess = session or make_nws_session()
    cache_key = f"{lat},{lon}"

    try:
        # Load persistent cache into memory once
        if not NWS_POINTS_CACHE:
            load_nws_points_cache()

        zone_alert_features = None
        try:
            point_metadata = get_nws_point_metadata(lat, lon, cache_key, location_name, sess)
            zone_ids = point_metadata.get('zone_ids', [])
            zone_alert_features = get_nws_alerts_by_zone(zone_ids, location_name, sess)
        except requests.exceptions.RequestException as metadata_error:
            logger.warning(f"Could not retrieve weather zone information for {location_name}: {metadata_error}")

        point_alerts_url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
        point_alert_features = None
        try:
            point_alert_features = fetch_nws_alert_features(sess, point_alerts_url, location_name)
            if point_alert_features:
                logger.info(f"NWS point-based match for {location_name}")
        except requests.exceptions.RequestException as point_error:
            logger.warning(f"Point-based NWS alert lookup failed for {location_name}: {point_error}")

        merged_features = merge_alert_features([zone_alert_features, point_alert_features])
        if merged_features:
            if zone_alert_features and point_alert_features:
                logger.info(
                    f"Found alerts for {location_name} using both weather zone and location point searches"
                )
            elif zone_alert_features:
                logger.info(f"Found alerts for {location_name} using weather zone search")
            return merged_features

        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error fetching NWS alerts for {location_name}: {e}")
        return None


def get_nws_forecast_periods_24h(lat, lon, location_name, session, now_utc=None):
    """Fetch forecast periods covering the next 24 hours for one US location."""
    reference_now = now_utc or datetime.now(UTC)
    cache_key = f"{lat},{lon}"

    if not NWS_POINTS_CACHE:
        load_nws_points_cache()

    try:
        point_metadata = get_nws_point_metadata(lat, lon, cache_key, location_name, session)
    except requests.exceptions.RequestException as metadata_error:
        logger.warning(f"Could not retrieve forecast metadata for {location_name}: {metadata_error}")
        return []

    forecast_urls = []
    hourly_url = point_metadata.get('forecast_hourly_url')
    regular_url = point_metadata.get('forecast_url')
    if hourly_url:
        forecast_urls.append(hourly_url)
    if regular_url and regular_url not in forecast_urls:
        forecast_urls.append(regular_url)

    if not forecast_urls:
        logger.warning(f"No forecast endpoints available for {location_name}")
        return []

    window_end = reference_now + timedelta(hours=24)

    for forecast_url in forecast_urls:
        try:
            response = session.get(forecast_url, timeout=10)
            response.raise_for_status()
            periods = response.json().get('properties', {}).get('periods', [])
            if not periods:
                continue

            upcoming_periods = []
            for period in periods:
                start_time = parse_iso_datetime(period.get('startTime'))
                end_time = parse_iso_datetime(period.get('endTime')) or start_time
                if not start_time:
                    continue
                if start_time < window_end and (end_time is None or end_time > reference_now):
                    upcoming_periods.append(period)

            if upcoming_periods:
                return upcoming_periods
        except requests.exceptions.RequestException as forecast_error:
            logger.warning(f"Forecast lookup failed for {location_name} ({forecast_url}): {forecast_error}")

    return []


def format_timeframe(start_time, end_time):
    """Format an approximate UTC timeframe for a risk summary."""
    if not start_time and not end_time:
        return "Next 24 hours"
    start_text = (start_time or end_time).strftime('%b %d %H:%M UTC')
    end_text = (end_time or start_time).strftime('%b %d %H:%M UTC')
    return f"{start_text} to {end_text}"


def parse_forecast_risks_24h(periods):
    """Infer practical 24h risk categories from NWS forecast periods."""
    category_matches = {category: [] for category in FORECAST_RISK_KEYWORDS}

    for period in periods:
        text_parts = [
            period.get('name', ''),
            period.get('shortForecast', ''),
            period.get('detailedForecast', ''),
            period.get('windSpeed', ''),
        ]
        combined_text = ' '.join(part for part in text_parts if part).lower()
        if not combined_text:
            continue

        start_time = parse_iso_datetime(period.get('startTime'))
        end_time = parse_iso_datetime(period.get('endTime')) or start_time
        snippet = (period.get('shortForecast') or period.get('detailedForecast') or period.get('name') or '').strip()
        if len(snippet) > 160:
            snippet = f"{snippet[:157]}..."
        evidence = {
            'name': period.get('name', 'Forecast Period'),
            'start': start_time,
            'end': end_time,
            'snippet': snippet,
        }

        for category, keywords in FORECAST_RISK_KEYWORDS.items():
            if any(keyword in combined_text for keyword in keywords):
                category_matches[category].append(evidence)

    active_categories = []
    all_matches = []
    for category, matches in category_matches.items():
        if matches:
            active_categories.append((category, len(matches)))
            all_matches.extend(matches)

    active_categories.sort(key=lambda item: (-item[1], item[0]))
    top_categories = [category for category, _ in active_categories[:3]]

    evidence_lines = []
    for category in top_categories:
        first_match = category_matches[category][0]
        evidence_lines.append(f"{category}: {first_match['name']} - {first_match['snippet']}")

    timeframe = "Next 24 hours"
    if all_matches:
        starts = [match['start'] for match in all_matches if match.get('start')]
        ends = [match['end'] for match in all_matches if match.get('end')]
        timeframe = format_timeframe(min(starts) if starts else None, max(ends) if ends else None)

    return {
        'has_elevated_risk': bool(top_categories),
        'top_categories': top_categories,
        'evidence': evidence_lines,
        'timeframe': timeframe,
    }


def build_risk_fingerprint(risk_summary):
    """Build stable fingerprint for per-location digest risk state."""
    source = json.dumps(
        {
            'top_categories': risk_summary.get('top_categories', []),
            'timeframe': risk_summary.get('timeframe', ''),
            'evidence': risk_summary.get('evidence', []),
        },
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def should_send_daily_digest(state, digest_hour_utc, now_utc):
    """Return True once/day at or after configured UTC digest hour."""
    if now_utc.hour < digest_hour_utc:
        return False
    today = now_utc.strftime('%Y-%m-%d')
    return state.get('last_digest_date_utc') != today


def classify_event_level(event_type):
    """Classify alert event type into warning/watch/advisory tiers."""
    text = (event_type or '').lower()
    if 'warning' in text:
        return 'warning'
    if 'watch' in text:
        return 'watch'
    if 'advisory' in text:
        return 'advisory'
    return 'other'


def build_immediate_escalation_fingerprint(nws_alerts):
    """Build comparable snapshot of current critical alert intensity."""
    events = sorted({a.get('event_type', '') for a in nws_alerts if a.get('event_type')})
    warning_events = sorted(
        {event for event in events if classify_event_level(event) == 'warning'}
    )
    max_severity = 0
    for alert in nws_alerts:
        severity = (alert.get('severity') or 'unknown').lower()
        max_severity = max(max_severity, SEVERITY_RANK.get(severity, 0))

    return {
        'events': events,
        'warning_events': warning_events,
        'max_severity': max_severity,
    }


def is_immediate_escalation(previous_fingerprint, current_fingerprint):
    """Return True when active critical alerts materially worsen."""
    current_events = set(current_fingerprint.get('events', []))
    if not current_events:
        return False

    if not previous_fingerprint:
        return True

    previous_events = set(previous_fingerprint.get('events', []))
    previous_warnings = set(previous_fingerprint.get('warning_events', []))
    current_warnings = set(current_fingerprint.get('warning_events', []))

    if current_fingerprint.get('max_severity', 0) > previous_fingerprint.get('max_severity', 0):
        return True
    if current_warnings - previous_warnings:
        return True
    if current_events - previous_events:
        return True
    if current_warnings and not previous_warnings:
        return True

    return False


def parse_nws_alerts(features):
    """Find critical alerts and prepare alert details for email.

    "Critical alerts" here means severe events such as tornadoes, floods,
    and other dangerous weather listed in CRITICAL_ALERT_TYPES.
    Matching uses a case-insensitive substring check.
    "Case-insensitive" means it matches words no matter how they are
    capitalized (for example, "tornado warning" or "Tornado Warning").
    A "substring check" means it looks for a critical alert name anywhere
    inside the full event text.
    It also allows extra words in the event text, such as
    "Tornado Warning for Northern Area".
    Returns a list of alert dictionaries (id, event_type, text, area).
    """
    alerts = []

    for feature in features:
        props = feature.get('properties', {})

        # Get alert details
        event = props.get('event', 'Unknown Alert')
        severity = props.get('severity', 'Unknown')
        headline = props.get('headline', '')
        effective = props.get('effective', '')
        expires = props.get('expires', '')
        area_desc = props.get('areaDesc', 'Unknown area')
        message_type = props.get('messageType', '')
        issue_time = props.get('sent', '') or props.get('onset', '')
        description = props.get('description', '')
        summary = props.get('summary', '')
        alert_id = build_nws_alert_id(feature, props, event, effective, expires, area_desc)

        event_lower = event.lower()
        is_critical_alert = any(critical in event_lower for critical in CRITICAL_ALERT_KEYWORDS)

        # ONLY include critical alert types
        if is_critical_alert:
            dedupe_key = build_alert_dedupe_key(event, headline, area_desc, effective, expires)
            alert_text = f"{event} ({severity})"
            if headline:
                alert_text += f"\n{headline}"
            if effective or expires:
                alert_text += f"\nEffective: {effective} | Expires: {expires}"
            alerts.append({
                'id': alert_id,
                'dedupe_key': dedupe_key,
                'event_type': event,
                'severity': severity,
                'text': alert_text,
                'area': area_desc,
                'effective': effective,
                'expires': expires,
                'message_type': message_type,
                'issue_time': issue_time,
                'description': description,
                'summary': summary,
            })
            logger.info(f"Critical alert identified: {event} for {area_desc}")
        else:
            logger.debug(f"Non-critical alert filtered out: {event}")

    return alerts


def build_nws_alert_id(feature, props, event, effective, expires, area_desc):
    """Create a unique ID for one NWS alert.

    First, this tries to use the official ID sent by NWS
    (for example: "NWS-ALERTS-AL12345").
    NWS may send that ID inside a full URL, and this function keeps only the
    last part of the URL so the saved key stays short and consistent.
    Example: from "https://api.weather.gov/alerts/NWS-ALERTS-AL12345",
    it keeps "NWS-ALERTS-AL12345".
    If NWS does not provide an ID, it builds a backup ID that stays the same
    for the same alert details by turning those details into a unique code
    using a SHA-256 hash function, so duplicate emails are avoided.
    Returns the alert ID as a string.
    """
    feature_id = feature.get('id', '') or props.get('id', '')
    alert_id = feature_id.split('/')[-1] if feature_id else ''

    if alert_id:
        return alert_id

    fallback_source = json.dumps(
        {
            'event': event,
            'effective': effective,
            'expires': expires,
            'area_desc': area_desc,
        },
        sort_keys=True,
        separators=(',', ':'),
    )
    return f"fallback-{hashlib.sha256(fallback_source.encode('utf-8')).hexdigest()}"


def build_alert_dedupe_key(event, headline, area_desc, effective, expires):
    """Create a stable dedupe key for an alert based on alert content."""
    source = json.dumps(
        {
            'event': (event or '').strip().lower(),
            'headline': (headline or '').strip().lower(),
            'area_desc': (area_desc or '').strip().lower(),
            'effective': (effective or '').strip().lower(),
            'expires': (expires or '').strip().lower(),
        },
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# OpenWeatherMap helpers (OCONUS — non-US locations)
# ---------------------------------------------------------------------------

def get_openweather_data(lat, lon, api_key, units='imperial'):
    """Fetch OpenWeatherMap One Call 3.0 payload for one location.

    Used for non-US (OCONUS) locations where NWS data is not available.
    Returns the full parsed JSON response dict.

    Parameters:
        lat: Latitude of the location.
        lon: Longitude of the location.
        api_key: OpenWeatherMap API key (OPENWEATHERMAP_API_KEY).
        units: Unit system — 'imperial' (default), 'metric', or 'standard'.

    Raises:
        ValueError: When api_key is missing.
        requests.HTTPError: On non-2xx HTTP response.
    """
    if not api_key:
        raise ValueError(
            "OPENWEATHERMAP_API_KEY is required for OCONUS (non-US) locations"
        )

    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": units,
        "exclude": "minutely",
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def parse_openweather_alerts(payload, location_name):
    """Normalize OpenWeatherMap alerts to the internal alert schema.

    Converts OWM ``alerts`` entries (if any) into the same dict shape used
    by ``parse_nws_alerts`` so the rest of the pipeline (dedupe, escalation,
    email) can handle them without modification.

    Parameters:
        payload: Full OWM One Call 3.0 response dict.
        location_name: Human-readable location name (used as area label and
            in the deterministic alert ID).

    Returns:
        List of normalized alert dicts.
    """
    normalized = []

    for alert in (payload.get('alerts') or []):
        event = alert.get('event', 'Weather Alert')
        sender = alert.get('sender_name', 'OpenWeatherMap')
        description = alert.get('description', '') or ''

        start_ts = alert.get('start')
        end_ts = alert.get('end')

        effective = datetime.fromtimestamp(start_ts, UTC).isoformat() if start_ts else ''
        expires = datetime.fromtimestamp(end_ts, UTC).isoformat() if end_ts else ''

        event_lower = event.lower()
        if any(k in event_lower for k in ('warning', 'hurricane', 'tornado')):
            severity = 'Severe'
        else:
            severity = 'Moderate'

        dedupe_key = build_alert_dedupe_key(
            event=event,
            headline=sender,
            area_desc=location_name,
            effective=effective,
            expires=expires,
        )

        alert_id_source = json.dumps(
            {
                'event': event,
                'sender': sender,
                'effective': effective,
                'expires': expires,
                'location': location_name,
            },
            sort_keys=True,
            separators=(',', ':'),
        )
        alert_id = f"owm-{hashlib.sha256(alert_id_source.encode('utf-8')).hexdigest()}"

        text = f"{event} ({severity})"
        text += f"\nSource: {sender}"
        if effective or expires:
            text += f"\nEffective: {effective} | Expires: {expires}"
        if description:
            text += f"\n{description}"

        normalized.append({
            'id': alert_id,
            'dedupe_key': dedupe_key,
            'event_type': event,
            'severity': severity,
            'text': text,
            'area': location_name,
            'effective': effective,
            'expires': expires,
            'message_type': 'Alert',
            'issue_time': effective,
            'description': description,
            'summary': '',
        })

    return normalized


def parse_openweather_risks_24h(payload):
    """Infer 24-hour risk categories from OpenWeatherMap current/hourly/daily fields.

    Mirrors ``parse_forecast_risks_24h`` but sources text from OWM weather
    condition objects rather than NWS forecast period text.

    Parameters:
        payload: Full OWM One Call 3.0 response dict.

    Returns:
        Dict with keys: has_elevated_risk, top_categories, evidence, timeframe.
    """
    category_hits = {k: [] for k in FORECAST_RISK_KEYWORDS}

    texts = []

    current = payload.get('current') or {}
    for w in (current.get('weather') or []):
        texts.append(f"{w.get('main', '')} {w.get('description', '')}")

    for h in (payload.get('hourly') or [])[:24]:
        for w in (h.get('weather') or []):
            texts.append(f"{w.get('main', '')} {w.get('description', '')}")

    for d in (payload.get('daily') or [])[:2]:
        if d.get('summary'):
            texts.append(d.get('summary', ''))
        for w in (d.get('weather') or []):
            texts.append(f"{w.get('main', '')} {w.get('description', '')}")

    combined = ' | '.join(t for t in texts if t).lower()

    for category, keywords in FORECAST_RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                category_hits[category].append(kw)

    top_categories = [c for c, hits in category_hits.items() if hits][:3]
    evidence = [
        f"{c}: matched keywords ({', '.join(category_hits[c][:3])})"
        for c in top_categories
    ]

    return {
        'has_elevated_risk': bool(top_categories),
        'top_categories': top_categories,
        'evidence': evidence,
        'timeframe': 'Next 24 hours',
    }


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
  • Sends one 24-hour risk digest daily (default 11:00 UTC)
  • Sends immediate emails only when active critical alerts escalate
  • Deduplication + state tracking reduce repeat noise

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


def send_run_summary_email(sender_email, sender_password, recipient_emails, run_alerts):
    """Send one email containing all new alerts found in this monitor run."""
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = f"🚨 Weather Monitor - Run Summary ({len(run_alerts)} new alerts)"

        lines = []
        for idx, a in enumerate(run_alerts, start=1):
            lines.append(f"{idx}. {a['location']} - {a['event_type']}")
            lines.append(f"   {a['text'].replace(chr(10), chr(10) + '   ')}")
            lines.append("")

        body = f"""
WEATHER MONITOR RUN SUMMARY
{'=' * 50}

Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}
New alerts in this run: {len(run_alerts)}

Details:
{chr(10).join(lines)}

This is an automated alert from Weather Monitor.
"""

        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        logger.info(f"Run summary email sent with {len(run_alerts)} alerts")
        return True
    except Exception as e:
        logger.error(f"Failed to send run summary email: {e}")
        return False


def send_daily_digest_email(sender_email, sender_password, recipient_emails, digest_rows):
    """Send one concise 24h risk digest email."""
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = f"📊 Weather Monitor - 24h Risk Digest ({len(digest_rows)} locations)"

        if digest_rows:
            lines = []
            for idx, row in enumerate(digest_rows, start=1):
                lines.append(f"{idx}. {row['location']}")
                lines.append(
                    f"   Priority: {row.get('priority_band', 'low').title()} "
                    f"(score {row.get('priority_score', 0)})"
                )
                lines.append(f"   Risks: {', '.join(row['top_categories'])}")
                lines.append(f"   Timeframe: {row['timeframe']}")
                if row.get('recommended_action'):
                    lines.append(f"   Recommended action: {row['recommended_action']}")
                if row.get('priority_reasons'):
                    lines.append(f"   Why this matters: {row['priority_reasons'][0]}")
                if row.get('operational_vulnerabilities'):
                    lines.append(
                        "   Site concerns: "
                        + '; '.join(row['operational_vulnerabilities'])
                    )
                if row.get('leadership_note'):
                    lines.append(f"   Leadership note: {row['leadership_note']}")
                for evidence in row['evidence']:
                    lines.append(f"   - {evidence}")
                lines.append("")
            details = '\n'.join(lines)
        else:
            details = "No elevated weather risks identified for monitored US locations in the next 24 hours."

        body = f"""
WEATHER MONITOR - 24 HOUR RISK DIGEST
{'=' * 50}

Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}
Locations with elevated risk: {len(digest_rows)}

{details}

This is an automated message from Weather Monitor.
"""

        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        logger.info(f"24h risk digest email sent with {len(digest_rows)} elevated-risk locations")
        return True
    except Exception as e:
        logger.error(f"Failed to send 24h risk digest email: {e}")
        return False


def _is_stale_alert(row):
    """Return True if an alert row should be treated as stale or inactive.

    An alert is stale when its message_type is 'Cancel' (case-insensitive) or
    when the combined text fields contain words that indicate it has been
    superseded, replaced, or cancelled.
    """
    message_type = (row.get('message_type', '') or '').strip().lower()
    if message_type == 'cancel':
        return True
    stale_keywords = ('superseded', 'replaced', 'canceled', 'cancelled')
    combined_text = ' '.join([
        row.get('description', '') or '',
        row.get('summary', '') or '',
        row.get('text', '') or '',
    ]).lower()
    return any(kw in combined_text for kw in stale_keywords)


def aggregate_escalation_alerts(rows):
    """Group, deduplicate, and sort escalation alert rows for email formatting.

    Takes a flat list of alert row dicts (each with at least 'location' and
    'event_type') and returns a list of location dicts, each containing a
    'threats' list of collapsed, tagged alert entries.

    Tags applied per event type within a location:
      [NEW]      - single active record for this event type.
      [UPDATED]  - multiple records; newest record's expiry is not later.
      [EXTENDED] - multiple records; newest record's expiry is later.

    Stale/cancelled alerts (message_type == 'Cancel' or text indicating
    superseded/replaced/canceled) are excluded before collapsing.

    Locations are sorted by total active threat count (descending), then by
    highest severity rank (descending).  Threats within each location are
    sorted by severity rank (descending).
    """
    # 1. Group rows by location
    by_location = {}
    for row in rows:
        loc = row.get('location', 'Unknown')
        by_location.setdefault(loc, []).append(row)

    location_results = []

    for loc_name, loc_rows in by_location.items():
        # 2. Filter stale/cancel records
        active_rows = [r for r in loc_rows if not _is_stale_alert(r)]
        if not active_rows:
            continue

        # 3. Group active rows by event type (case-insensitive key)
        by_event = {}
        for row in active_rows:
            event_type = (row.get('event_type') or row.get('event', 'Unknown')).strip()
            event_key = event_type.lower()
            by_event.setdefault(event_key, []).append(row)

        threats = []
        for _event_key, event_rows in by_event.items():
            # Preserve original casing from the first row's event_type
            display_event = (
                event_rows[0].get('event_type') or event_rows[0].get('event', 'Unknown')
            ).strip()

            if len(event_rows) == 1:
                row = event_rows[0]
                threat = {
                    'event_type': display_event,
                    'severity': row.get('severity', 'Unknown'),
                    'tag': '[NEW]',
                    'effective': row.get('effective', ''),
                    'expires': row.get('expires', ''),
                    'original_expires': None,
                    'note': None,
                }
            else:
                # Sort ascending by issue_time (preferred) then effective to find newest
                sorted_rows = sorted(
                    event_rows,
                    key=lambda r: r.get('issue_time', '') or r.get('effective', '') or '',
                )
                oldest = sorted_rows[0]
                newest = sorted_rows[-1]

                oldest_expires = oldest.get('expires', '') or ''
                newest_expires = newest.get('expires', '') or ''

                if newest_expires and oldest_expires and newest_expires > oldest_expires:
                    tag = '[EXTENDED]'
                    note = f"Extended from {oldest_expires} to {newest_expires}"
                    original_expires = oldest_expires
                else:
                    tag = '[UPDATED]'
                    note = None
                    original_expires = None

                threat = {
                    'event_type': display_event,
                    'severity': newest.get('severity', 'Unknown'),
                    'tag': tag,
                    'effective': newest.get('effective', ''),
                    'expires': newest.get('expires', ''),
                    'original_expires': original_expires,
                    'note': note,
                }

            threats.append(threat)

        # 4. Sort threats by severity descending
        threats.sort(
            key=lambda t: SEVERITY_RANK.get((t.get('severity') or 'unknown').lower(), 0),
            reverse=True,
        )

        max_sev = max(
            (SEVERITY_RANK.get((t.get('severity') or 'unknown').lower(), 0) for t in threats),
            default=0,
        )
        location_results.append({
            'location': loc_name,
            'threats': threats,
            'total_threats': len(threats),
            'max_severity_rank': max_sev,
        })

    # 5. Sort locations: total threats descending, then max severity rank descending
    location_results.sort(
        key=lambda x: (x['total_threats'], x['max_severity_rank']),
        reverse=True,
    )

    return location_results


def send_immediate_escalation_email(sender_email, sender_password, recipient_emails, escalation_rows):
    """Send one immediate escalation alert email for materially worsened risk."""
    try:
        aggregated = aggregate_escalation_alerts(escalation_rows)
        location_count = len(aggregated)

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = f"🚨 Weather Monitor - Immediate Escalation Alert ({location_count} locations)"

        lines = []
        for idx, loc in enumerate(aggregated, start=1):
            loc_name = loc['location']
            threats = loc['threats']
            threat_count = loc['total_threats']
            noun = 'threat' if threat_count == 1 else 'threats'
            lines.append(f"{idx}. {loc_name} [{threat_count} active {noun}]")
            for threat in threats:
                tag = threat['tag']
                event_type = threat['event_type']
                severity = threat.get('severity', 'Unknown')
                effective = threat.get('effective', '')
                expires = threat.get('expires', '')
                note = threat.get('note')
                lines.append(f"   * {tag} {event_type} | Severity: {severity}")
                if effective or expires:
                    lines.append(f"     Effective: {effective}, Expires: {expires}")
                if note:
                    lines.append(f"     {note}")
            lines.append("")

        body = f"""
WEATHER MONITOR - IMMEDIATE ESCALATION ALERT
{'=' * 50}

Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}
Active threat locations: {location_count}

{chr(10).join(lines)}
---
This is an automated alert from Weather Monitor. Review NWS alerts at weather.gov.
"""

        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        logger.info(f"Immediate escalation email sent with {location_count} locations")
        return True
    except Exception as e:
        logger.error(f"Failed to send immediate escalation email: {e}")
        return False


# ---------------------------------------------------------------------------
# Executive priority engine
# ---------------------------------------------------------------------------

def score_location_priority(
    active_alerts,
    risk_summary,
    is_escalating,
    location_weight=1.0,
    hazard_weights=None,
):
    """Compute deterministic priority score (0-100), band, status, and confidence.

    Inputs
    ------
    active_alerts   : list of dicts from parse_nws_alerts()
    risk_summary    : dict from parse_forecast_risks_24h()
    is_escalating   : bool — True when is_immediate_escalation() fires this run
    location_weight : optional per-location multiplier from config (default 1.0)

    Returns
    -------
    (score: int, band: str, status: str, confidence: float)

    Scoring model (all weights are config-overridable via env vars):
      1. Severity contribution  — _W_SEVERITY value added per active alert
      2. Event-type bonus       — best matching key in _W_EVENT_BONUS per alert
         (at most one bonus per alert; first match wins)
      3. Forecast risk bonus    — _W_RISK_CAT_BONUS × category count,
         capped at _W_RISK_CAT_MAX
      4. Escalation bonus       — _W_ESCALATION_BONUS added when is_escalating
      5. location_weight        — multiplier applied before capping at 100

    Band thresholds (configurable):
      critical : score >= PRIORITY_CRITICAL_MIN  (default 85)
      high     : score >= PRIORITY_HIGH_MIN       (default 65)
      medium   : score >= PRIORITY_MEDIUM_MIN     (default 40)
      low      : below PRIORITY_MEDIUM_MIN

    Status rules (deterministic, evaluated in priority order):
      escalating : is_escalating is True
      active     : active_alerts is non-empty
      elevated   : risk_summary has_elevated_risk is True
      normal     : none of the above
    """
    score = 0.0
    hazard_weights = hazard_weights or {}

    for a in active_alerts:
        sev = (a.get('severity') or 'unknown').lower()
        alert_points = float(_W_SEVERITY.get(sev, 0))
        e = (a.get('event_type') or '').lower()
        for key, bonus in _W_EVENT_BONUS.items():
            if key in e:
                alert_points += bonus
                break  # at most one event-type bonus per alert
        alert_category = classify_alert_hazard(a.get('event_type', ''))
        alert_points *= get_hazard_weight_multiplier(hazard_weights, alert_category)
        score += alert_points

    weighted_risk_bonus = 0.0
    max_risk_multiplier = 1.0
    for category in risk_summary.get('top_categories', []):
        risk_multiplier = get_hazard_weight_multiplier(hazard_weights, category)
        weighted_risk_bonus += _W_RISK_CAT_BONUS * risk_multiplier
        max_risk_multiplier = max(max_risk_multiplier, risk_multiplier)
    score += min(weighted_risk_bonus, _W_RISK_CAT_MAX * max_risk_multiplier)

    if is_escalating:
        score += _W_ESCALATION_BONUS

    score = int(min(100, round(score * _read_numeric_weight(location_weight, default=1.0, minimum=0.0))))

    if score >= PRIORITY_CRITICAL_MIN:
        band = 'critical'
    elif score >= PRIORITY_HIGH_MIN:
        band = 'high'
    elif score >= PRIORITY_MEDIUM_MIN:
        band = 'medium'
    else:
        band = 'low'

    if is_escalating:
        status = 'escalating'
    elif active_alerts:
        status = 'active'
    elif risk_summary.get('has_elevated_risk'):
        status = 'elevated'
    else:
        status = 'normal'

    # Confidence: base 0.55, boosted by data availability
    confidence = 0.55
    if active_alerts:
        confidence += 0.25
    if risk_summary.get('has_elevated_risk'):
        confidence += 0.15
    if is_escalating:
        confidence += 0.05
    confidence = min(0.99, round(confidence, 2))

    return score, band, status, confidence


def get_recommended_action(priority_band, status):
    """Return a concise, operations-focused action recommendation for senior management.

    Language is generated deterministically from priority band and current status
    so that operators can act without interpreting raw weather data.
    """
    if priority_band == 'critical':
        if status == 'escalating':
            return (
                "IMMEDIATE ACTION: Activate emergency response protocol; verify personnel "
                "shelter posture and accountability now."
            )
        return (
            "Activate emergency response procedures; confirm personnel accountability "
            "and escalate to senior leadership."
        )
    if priority_band == 'high':
        if status == 'escalating':
            return (
                "Implement enhanced safety protocols; brief site leadership on current "
                "threat and prepare contingency actions."
            )
        return (
            "Monitor closely; brief site leadership; ensure emergency contacts are current "
            "and contingency plans are ready."
        )
    if priority_band == 'medium':
        return (
            "Review forecast details; confirm emergency contacts are current; "
            "monitor for escalation."
        )
    # low
    return "No action required; continue routine monitoring."


# ---------------------------------------------------------------------------
# Dashboard JSON artifact
# ---------------------------------------------------------------------------

def build_dashboard_digest(now_utc, locations_payload, delivery, changes, errors=None):
    """Assemble the executive dashboard JSON artifact for one monitor run.

    Parameters
    ----------
    now_utc          : datetime (UTC-aware) for this run
    locations_payload: list of per-location dicts built in main()
    delivery         : dict summarising email send outcomes
    changes          : dict with new_escalations / resolved_locations / unchanged_locations
    errors           : optional list of error strings recorded during the run

    Returns a dict ready to be serialised to dashboard_digest.json.
    """
    priority_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    elevated = 0
    active_critical = 0
    escalating = 0

    for row in locations_payload:
        band = row.get('priority_band', 'low')
        if band in priority_counts:
            priority_counts[band] += 1
        if row.get('risk_categories'):
            elevated += 1
        if row.get('active_alerts_count', 0) > 0:
            active_critical += 1
        if row.get('status') == 'escalating':
            escalating += 1

    top_locations = sorted(
        locations_payload,
        key=lambda x: (x.get('priority_score', 0), x.get('active_alerts_count', 0)),
        reverse=True,
    )[:10]

    run_ts = now_utc.strftime('%Y%m%dT%H%M%SZ')
    run_hash = hashlib.sha1(run_ts.encode()).hexdigest()[:8]

    return {
        'run_id': f"{run_ts}_{run_hash}",
        'generated_at_utc': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'digest_window': {
            'type': 'next_24h',
            'start_utc': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'end_utc': (now_utc + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        },
        'summary': {
            'locations_total': len(locations_payload),
            'locations_with_elevated_risk': elevated,
            'locations_with_active_critical_alerts': active_critical,
            'locations_escalating': escalating,
            'priority_counts': priority_counts,
        },
        'top_locations': top_locations,
        'locations': locations_payload,
        'changes_since_last_run': changes,
        'delivery': delivery,
        'errors': errors or [],
    }


def save_dashboard_digest(payload):
    """Write dashboard digest JSON to DASHBOARD_DIGEST_FILE."""
    try:
        with open(DASHBOARD_DIGEST_FILE, 'w') as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Dashboard digest written to {DASHBOARD_DIGEST_FILE}")
    except Exception as e:
        logger.error(f"Failed to write dashboard digest JSON: {e}")


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

    daily_digest_enabled = read_bool_setting(config, 'daily_digest_enabled', True)
    daily_digest_hour_utc = max(0, min(23, read_int_setting(config, 'daily_digest_hour_utc', 11)))
    digest_send_if_empty = read_bool_setting(config, 'digest_send_if_empty', False)
    immediate_alerts_enabled = read_bool_setting(config, 'immediate_alerts_enabled', True)
    immediate_escalation_only = read_bool_setting(config, 'immediate_escalation_only', True)

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
    monitor_state = load_monitor_state()
    immediate_state = monitor_state.setdefault('last_immediate_escalation_fingerprint_by_location', {})

    now_utc = datetime.now(UTC)
    immediate_email_rows = []
    digest_rows = []
    digest_fingerprints = {}
    alerts_sent = 0
    # Dashboard / priority tracking
    locations_payload = []
    prior_signatures = monitor_state.get('prior_location_signatures', {})
    current_signatures = {}
    run_errors = []

    # Check weather for each location
    for location in locations:
        location_name = location.get('name', 'Unknown')
        lat = location.get('lat')
        lon = location.get('lon')
        country = location.get('country', 'XX')
        priority_profile = get_location_priority_profile(location)
        location_weight = priority_profile['priority_weight']
        hazard_weights = priority_profile['hazard_weights']
        operational_vulnerabilities = priority_profile['operational_vulnerabilities']
        leadership_note = priority_profile['leadership_note']

        if lat is None or lon is None:
            logger.warning(f"Invalid coordinates for {location_name}")
            continue

        logger.info(f"Checking alerts for {location_name} ({country})...")

        try:
            # Check if this is a US location - use NWS alerts
            if country.upper() == 'US':
                logger.info(f"Fetching National Weather Service alerts for {location_name}...")
                nws_features = get_nws_alerts(lat, lon, location_name, session=nws_session)
                nws_alerts = parse_nws_alerts(nws_features) if nws_features else []

                current_immediate_fp = build_immediate_escalation_fingerprint(nws_alerts)
                previous_immediate_fp = immediate_state.get(location_name)
                location_escalation = is_immediate_escalation(previous_immediate_fp, current_immediate_fp)
                location_new_alert_rows = []
                location_new_alert_keys = []

                if nws_alerts:
                    for alert_data in nws_alerts:
                        event_type = alert_data.get('event_type', 'NWS Alert')
                        alert_dedupe_key = alert_data.get('dedupe_key') or alert_data.get('id', '')
                        alert_text = alert_data.get('text', '')
                        alert_key = f"{location_name}_{alert_dedupe_key}"

                        if alert_key not in sent_alerts:
                            location_new_alert_rows.append({
                                'location': location_name,
                                'event_type': event_type,
                                'text': alert_text,
                            })
                            location_new_alert_keys.append(alert_key)
                        else:
                            logger.debug(f"Alert already processed: {alert_key}")

                    should_add_immediate_rows = (
                        (immediate_escalation_only and location_escalation) or
                        (not immediate_escalation_only and bool(location_new_alert_rows))
                    )
                    if immediate_alerts_enabled and should_add_immediate_rows:
                        for alert_data in nws_alerts:
                            immediate_email_rows.append({
                                'location': location_name,
                                'event_type': alert_data.get('event_type', 'NWS Alert'),
                                'severity': alert_data.get('severity', 'Unknown'),
                                'text': alert_data.get('text', ''),
                                'effective': alert_data.get('effective', ''),
                                'expires': alert_data.get('expires', ''),
                                'issue_time': alert_data.get('issue_time', ''),
                                'message_type': alert_data.get('message_type', ''),
                                'description': alert_data.get('description', ''),
                                'summary': alert_data.get('summary', ''),
                            })
                        for alert_key in location_new_alert_keys:
                            sent_alerts[alert_key] = now_utc.isoformat()
                            alerts_sent += 1
                        immediate_state[location_name] = current_immediate_fp
                    elif immediate_escalation_only and location_escalation:
                        logger.info(
                            f"Escalation detected for {location_name}, but immediate alerts are disabled by config."
                        )
                    else:
                        logger.info(f"No immediate escalation for {location_name}")
                else:
                    logger.info(f"No critical alerts for {location_name}")
                    immediate_state.pop(location_name, None)

                forecast_periods = get_nws_forecast_periods_24h(lat, lon, location_name, nws_session, now_utc=now_utc)
                risk_summary = parse_forecast_risks_24h(forecast_periods)
                digest_fingerprints[location_name] = build_risk_fingerprint(risk_summary)

                # --- Executive priority scoring for dashboard ---
                # Optional per-location multiplier: add "priority_weight": 1.5 (or any positive
                # float) to a location entry in config.json to amplify its score; use 0.5 to
                # de-emphasise it.  Omit the key (or set to 1.0) for standard behaviour.
                priority_score, priority_band, loc_status, confidence = score_location_priority(
                    nws_alerts, risk_summary, location_escalation, location_weight, hazard_weights
                )
                recommended_action = get_recommended_action(priority_band, loc_status)
                priority_reasons = build_priority_reasons(
                    nws_alerts,
                    risk_summary,
                    location_escalation,
                    hazard_weights,
                    operational_vulnerabilities,
                    leadership_note,
                )
                current_signatures[location_name] = {
                    'band': priority_band,
                    'status': loc_status,
                    'score': priority_score,
                }
                if risk_summary['has_elevated_risk']:
                    digest_rows.append({
                        'location': location_name,
                        'top_categories': risk_summary['top_categories'],
                        'evidence': risk_summary['evidence'],
                        'timeframe': risk_summary['timeframe'],
                        'priority_score': priority_score,
                        'priority_band': priority_band,
                        'recommended_action': recommended_action,
                        'priority_reasons': priority_reasons,
                        'operational_vulnerabilities': operational_vulnerabilities,
                        'leadership_note': leadership_note,
                    })
                dash_alerts = [
                    {
                        'id': a.get('id', ''),
                        'event_type': a.get('event_type', ''),
                        'severity': a.get('severity', ''),
                        'area': a.get('area', ''),
                        'effective': a.get('effective', ''),
                        'expires': a.get('expires', ''),
                    }
                    for a in nws_alerts
                ]
                locations_payload.append({
                    'location': location_name,
                    'lat': lat,
                    'lon': lon,
                    'country': country,
                    'status': loc_status,
                    'priority_score': priority_score,
                    'priority_band': priority_band,
                    'confidence': confidence,
                    'risk_categories': risk_summary.get('top_categories', []),
                    'risk_evidence': risk_summary.get('evidence', []),
                    'timeframe': risk_summary.get('timeframe', ''),
                    'active_alerts_count': len(nws_alerts),
                    'active_alerts': dash_alerts,
                    'applied_hazard_weights': hazard_weights,
                    'operational_vulnerabilities': operational_vulnerabilities,
                    'leadership_note': leadership_note,
                    'priority_reasons': priority_reasons,
                    'recommended_action': recommended_action,
                    'last_change_utc': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
            else:
                # Non-US location — use OpenWeatherMap One Call 3.0
                logger.info(f"Fetching OpenWeatherMap alerts for {location_name}...")
                try:
                    owm_payload = get_openweather_data(
                        lat, lon, config.get('openweathermap_api_key')
                    )
                except Exception as owm_err:
                    logger.warning(
                        f"OWM lookup failed for {location_name} ({type(owm_err).__name__}: {owm_err}). "
                        "Check that OPENWEATHERMAP_API_KEY is set and valid for OCONUS locations."
                    )
                    owm_payload = {}

                owm_alerts = parse_openweather_alerts(owm_payload, location_name) if owm_payload else []

                current_immediate_fp = build_immediate_escalation_fingerprint(owm_alerts)
                previous_immediate_fp = immediate_state.get(location_name)
                location_escalation = is_immediate_escalation(previous_immediate_fp, current_immediate_fp)
                location_new_alert_keys = []

                if owm_alerts:
                    for alert_data in owm_alerts:
                        alert_dedupe_key = alert_data.get('dedupe_key') or alert_data.get('id', '')
                        alert_key = f"{location_name}_{alert_dedupe_key}"
                        if alert_key not in sent_alerts:
                            location_new_alert_keys.append(alert_key)
                        else:
                            logger.debug(f"Alert already processed: {alert_key}")

                    should_add_immediate_rows = (
                        (immediate_escalation_only and location_escalation) or
                        (not immediate_escalation_only and bool(location_new_alert_keys))
                    )
                    if immediate_alerts_enabled and should_add_immediate_rows:
                        for alert_data in owm_alerts:
                            immediate_email_rows.append({
                                'location': location_name,
                                'event_type': alert_data.get('event_type', 'Weather Alert'),
                                'severity': alert_data.get('severity', 'Unknown'),
                                'text': alert_data.get('text', ''),
                                'effective': alert_data.get('effective', ''),
                                'expires': alert_data.get('expires', ''),
                                'issue_time': alert_data.get('issue_time', ''),
                                'message_type': alert_data.get('message_type', ''),
                                'description': alert_data.get('description', ''),
                                'summary': alert_data.get('summary', ''),
                            })
                        for alert_key in location_new_alert_keys:
                            sent_alerts[alert_key] = now_utc.isoformat()
                            alerts_sent += 1
                        immediate_state[location_name] = current_immediate_fp
                    elif immediate_escalation_only and location_escalation:
                        logger.info(
                            f"Escalation detected for {location_name}, but immediate alerts are disabled by config."
                        )
                    else:
                        logger.info(f"No immediate escalation for {location_name}")
                else:
                    logger.info(f"No OWM alerts for {location_name}")
                    immediate_state.pop(location_name, None)

                risk_summary = parse_openweather_risks_24h(owm_payload) if owm_payload else {
                    'has_elevated_risk': False,
                    'top_categories': [],
                    'evidence': [],
                    'timeframe': 'Next 24 hours',
                }
                digest_fingerprints[location_name] = build_risk_fingerprint(risk_summary)

                priority_score, priority_band, loc_status, confidence = score_location_priority(
                    owm_alerts, risk_summary, location_escalation, location_weight, hazard_weights
                )
                recommended_action = get_recommended_action(priority_band, loc_status)
                priority_reasons = build_priority_reasons(
                    owm_alerts,
                    risk_summary,
                    location_escalation,
                    hazard_weights,
                    operational_vulnerabilities,
                    leadership_note,
                )
                current_signatures[location_name] = {
                    'band': priority_band,
                    'status': loc_status,
                    'score': priority_score,
                }
                if risk_summary['has_elevated_risk']:
                    digest_rows.append({
                        'location': location_name,
                        'top_categories': risk_summary['top_categories'],
                        'evidence': risk_summary['evidence'],
                        'timeframe': risk_summary['timeframe'],
                        'priority_score': priority_score,
                        'priority_band': priority_band,
                        'recommended_action': recommended_action,
                        'priority_reasons': priority_reasons,
                        'operational_vulnerabilities': operational_vulnerabilities,
                        'leadership_note': leadership_note,
                    })
                dash_alerts = [
                    {
                        'id': a.get('id', ''),
                        'event_type': a.get('event_type', ''),
                        'severity': a.get('severity', ''),
                        'area': a.get('area', ''),
                        'effective': a.get('effective', ''),
                        'expires': a.get('expires', ''),
                    }
                    for a in owm_alerts
                ]
                locations_payload.append({
                    'location': location_name,
                    'lat': lat,
                    'lon': lon,
                    'country': country,
                    'status': loc_status,
                    'priority_score': priority_score,
                    'priority_band': priority_band,
                    'confidence': confidence,
                    'risk_categories': risk_summary.get('top_categories', []),
                    'risk_evidence': risk_summary.get('evidence', []),
                    'timeframe': risk_summary.get('timeframe', ''),
                    'active_alerts_count': len(owm_alerts),
                    'active_alerts': dash_alerts,
                    'applied_hazard_weights': hazard_weights,
                    'operational_vulnerabilities': operational_vulnerabilities,
                    'leadership_note': leadership_note,
                    'priority_reasons': priority_reasons,
                    'recommended_action': recommended_action,
                    'last_change_utc': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
        except Exception as exc:
            logger.error(f"Unexpected error processing {location_name}: {exc}")
            run_errors.append(f"{location_name}: {exc}")

    digest_rows.sort(
        key=lambda row: (
            row.get('priority_score', 0),
            len(row.get('top_categories', [])),
            row.get('location', ''),
        ),
        reverse=True,
    )

    # --- Change tracking: compare current signatures against prior run ---
    band_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
    new_escalations = []
    new_locations = []
    resolved_locations = []
    unchanged_locations = []
    for loc_name, sig in current_signatures.items():
        prior = prior_signatures.get(loc_name)
        if prior is None:
            # First time this location has been seen; report it if already active/elevated
            if sig['status'] not in ('normal',):
                new_locations.append(loc_name)
            continue
        cur_band = sig['band']
        prior_band = prior.get('band', 'low')
        cur_status = sig['status']
        prior_status = prior.get('status', 'normal')
        if band_order.get(cur_band, 0) > band_order.get(prior_band, 0):
            new_escalations.append(loc_name)
        elif cur_status == 'normal' and prior_status != 'normal':
            resolved_locations.append(loc_name)
        else:
            unchanged_locations.append(loc_name)

    changes = {
        'new_escalations': new_escalations,
        'new_locations': new_locations,
        'resolved_locations': resolved_locations,
        'unchanged_locations': unchanged_locations,
        'new_escalation_count': len(new_escalations),
        'new_location_count': len(new_locations),
        'resolved_count': len(resolved_locations),
        'unchanged_count': len(unchanged_locations),
    }

    # --- Send emails; capture delivery outcomes for dashboard ---
    digest_sent = False
    digest_recipients = 0

    if daily_digest_enabled and should_send_daily_digest(monitor_state, daily_digest_hour_utc, now_utc):
        if digest_rows or digest_send_if_empty:
            digest_sent = send_daily_digest_email(
                config['sender_email'],
                config['sender_password'],
                recipient_emails,
                digest_rows
            )
            digest_recipients = len(recipient_emails)
        else:
            logger.info("Digest hour reached; no elevated 24h risks found, digest email skipped.")
        monitor_state['last_digest_date_utc'] = now_utc.strftime('%Y-%m-%d')
        monitor_state['last_digest_fingerprint_by_location'] = digest_fingerprints
    else:
        logger.info("Daily digest not sent in this run (disabled, not scheduled yet, or already sent today).")

    immediate_sent = False
    immediate_rows_count = 0

    if immediate_alerts_enabled and immediate_email_rows:
        immediate_sent = send_immediate_escalation_email(
            config['sender_email'],
            config['sender_password'],
            recipient_emails,
            immediate_email_rows
        )
        immediate_rows_count = len(immediate_email_rows)
    elif not immediate_alerts_enabled:
        logger.info("Immediate alerts are disabled by configuration.")
    else:
        logger.info("No immediate escalation alerts to email in this run.")

    # --- Build and write dashboard digest JSON ---
    delivery = {
        'digest_email_sent': digest_sent,
        'digest_email_recipients': digest_recipients,
        'immediate_email_sent': immediate_sent,
        'immediate_email_rows': immediate_rows_count,
        'immediate_email_recipients': len(recipient_emails) if immediate_sent else 0,
    }
    dashboard = build_dashboard_digest(now_utc, locations_payload, delivery, changes, run_errors)
    save_dashboard_digest(dashboard)

    # Save sent alerts
    save_sent_alerts(sent_alerts)
    # Persist updated location signatures for next-run change tracking
    monitor_state['prior_location_signatures'] = current_signatures
    save_monitor_state(monitor_state)

    logger.info(f"Alert check complete. Critical alerts sent: {alerts_sent}")


if __name__ == '__main__':
    main()
