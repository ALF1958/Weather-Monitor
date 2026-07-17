#!/usr/bin/env python3
"""
Weather Monitor - Alerts for Severe Weather
Monitors multiple locations and sends email alerts for severe weather conditions
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

# Severe weather conditions to monitor
SEVERE_WEATHER = {
    'Tornado',
    'Flood',
    'Severe Thunderstorm',
    'Hurricane',
    'Winter Storm',
    'Extreme Cold',
    'Extreme Heat',
    'Lightning',
    'Hail',
    'Blizzard',
    'Severe',
    'Warning',
    'Alert'
}

# Track sent alerts to avoid duplicates
SENT_ALERTS_FILE = 'sent_alerts.json'


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
        'locations': [
            {'name': 'New York, USA', 'lat': 40.7128, 'lon': -74.0060},
            {'name': 'London, UK', 'lat': 51.5074, 'lon': -0.1278},
            {'name': 'Tokyo, Japan', 'lat': 35.6762, 'lon': 139.6503},
            {'name': 'Sydney, Australia', 'lat': -33.8688, 'lon': 151.2093},
            {'name': 'Toronto, Canada', 'lat': 43.6532, 'lon': -79.3832},
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


def get_weather(api_key, lat, lon, location_name):
    """Fetch weather data from OpenWeatherMap API"""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather for {location_name}: {e}")
        return None


def check_severe_weather(weather_data):
    """Check if weather contains severe conditions"""
    if not weather_data:
        return None
    
    conditions = []
    
    # Check main weather condition
    main = weather_data.get('weather', [{}])[0].get('main', '').lower()
    description = weather_data.get('weather', [{}])[0].get('description', '').lower()
    
    # Check for severe weather keywords
    for condition in SEVERE_WEATHER:
        if condition.lower() in main or condition.lower() in description:
            conditions.append(weather_data.get('weather', [{}])[0].get('description', condition))
    
    # Check temperature extremes
    temp_k = weather_data.get('main', {}).get('temp', 0)
    temp_c = temp_k - 273.15
    
    if temp_c < -30:
        conditions.append(f"Extreme Cold ({temp_c:.1f}°C)")
    elif temp_c > 45:
        conditions.append(f"Extreme Heat ({temp_c:.1f}°C)")
    
    # Check wind speed (hurricane threshold ~32.7 m/s)
    wind_speed = weather_data.get('wind', {}).get('speed', 0)
    if wind_speed > 32.7:
        conditions.append(f"Hurricane-force winds ({wind_speed:.1f} m/s)")
    
    return conditions if conditions else None


def send_alert_email(sender_email, sender_password, recipient_emails, location_name, conditions):
    """Send email alert for severe weather"""
    try:
        # Create email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(recipient_emails)
        msg['Subject'] = f"🚨 SEVERE WEATHER ALERT - {location_name}"
        
        # Email body
        conditions_list = '\n'.join([f"  • {c}" for c in conditions])
        body = f"""
SEVERE WEATHER ALERT
====================

Location: {location_name}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Detected Conditions:
{conditions_list}

This is an automated alert from Weather Monitor.
Please take appropriate safety measures.
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        logger.info(f"Alert sent for {location_name}: {', '.join(conditions)}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


def main():
    """Main weather monitoring loop"""
    logger.info("Starting weather check for multiple locations...")
    
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
        
        if lat is None or lon is None:
            logger.warning(f"Invalid coordinates for {location_name}")
            continue
        
        logger.info(f"Checking weather for {location_name}...")
        
        # Get weather data
        weather_data = get_weather(
            config['openweathermap_api_key'],
            lat,
            lon,
            location_name
        )
        
        if not weather_data:
            continue
        
        # Check for severe weather
        severe_conditions = check_severe_weather(weather_data)
        
        if severe_conditions:
            # Create alert key to avoid duplicates
            alert_key = f"{location_name}_{datetime.now().strftime('%Y-%m-%d')}"
            
            if alert_key not in sent_alerts:
                # Send email alert
                if send_alert_email(
                    config['sender_email'],
                    config['sender_password'],
                    recipient_emails,
                    location_name,
                    severe_conditions
                ):
                    sent_alerts[alert_key] = datetime.now().isoformat()
                    alerts_sent += 1
            else:
                logger.info(f"Alert already sent for {location_name} today, skipping duplicate")
    
    # Save sent alerts
    save_sent_alerts(sent_alerts)
    
    logger.info(f"Weather check complete. Alerts sent: {alerts_sent}")


if __name__ == '__main__':
    main()
