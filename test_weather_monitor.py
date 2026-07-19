import unittest
from unittest.mock import Mock, patch

import requests

import weather_monitor


class TestGetNwsAlerts(unittest.TestCase):
    def setUp(self):
        weather_monitor.NWS_POINTS_CACHE = {}

    @patch("weather_monitor.load_nws_points_cache")
    @patch("weather_monitor.save_nws_points_cache")
    def test_get_nws_alerts_uses_zone_first_then_point(self, mock_save_cache, mock_load_cache):
        session = Mock()
        points_response = Mock()
        points_response.raise_for_status.return_value = None
        points_response.json.return_value = {
            "properties": {
                "forecastZone": "https://api.weather.gov/zones/forecast/KYZ007",
                "county": "https://api.weather.gov/zones/county/KYC047",
            }
        }

        forecast_zone_response = Mock()
        forecast_zone_response.raise_for_status.return_value = None
        forecast_zone_response.json.return_value = {
            "features": [{"id": "zone-alert-1", "properties": {"event": "Flood Warning"}}]
        }

        county_zone_response = Mock()
        county_zone_response.raise_for_status.return_value = None
        county_zone_response.json.return_value = {"features": []}

        point_response = Mock()
        point_response.raise_for_status.return_value = None
        point_response.json.return_value = {
            "features": [{"id": "point-alert-1", "properties": {"event": "Severe Thunderstorm Warning"}}]
        }

        session.get.side_effect = [
            points_response,
            forecast_zone_response,
            county_zone_response,
            point_response,
        ]

        features = weather_monitor.get_nws_alerts(36.6260, -87.4660, "Fort Campbell", session=session)

        # Extract alert IDs to verify both zone and point alerts are present.
        self.assertEqual(
            [f["id"] for f in features],
            ["zone-alert-1", "point-alert-1"]
        )
        self.assertEqual(
            session.get.call_args_list[0].args[0],
            "https://api.weather.gov/points/36.626,-87.466",
        )
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://api.weather.gov/alerts/active?zone=KYZ007",
        )
        self.assertEqual(
            session.get.call_args_list[2].args[0],
            "https://api.weather.gov/alerts/active?zone=KYC047",
        )
        self.assertEqual(
            session.get.call_args_list[3].args[0],
            "https://api.weather.gov/alerts/active?point=36.626,-87.466",
        )
        self.assertIn("36.626,-87.466", weather_monitor.NWS_POINTS_CACHE)
        self.assertEqual(
            weather_monitor.NWS_POINTS_CACHE["36.626,-87.466"]["zone_ids"],
            ["KYZ007", "KYC047"]
        )
        mock_load_cache.assert_called_once()
        mock_save_cache.assert_called_once()

    @patch("weather_monitor.load_nws_points_cache")
    @patch("weather_monitor.save_nws_points_cache")
    def test_get_nws_alerts_returns_zone_alerts_when_point_lookup_fails(self, mock_save_cache, mock_load_cache):
        session = Mock()

        points_response = Mock()
        points_response.raise_for_status.return_value = None
        points_response.json.return_value = {
            "properties": {
                "forecastZone": "https://api.weather.gov/zones/forecast/KYZ007",
                "county": "https://api.weather.gov/zones/county/KYC047",
            }
        }

        zone_response = Mock()
        zone_response.raise_for_status.return_value = None
        zone_response.json.return_value = {
            "features": [{"id": "zone-alert-1", "properties": {"event": "Flood Warning"}}]
        }

        no_alerts_response = Mock()
        no_alerts_response.raise_for_status.return_value = None
        no_alerts_response.json.return_value = {"features": []}

        point_failure = requests.exceptions.RequestException("point lookup failed")
        session.get.side_effect = [points_response, zone_response, no_alerts_response, point_failure]

        features = weather_monitor.get_nws_alerts(36.6260, -87.4660, "Fort Campbell", session=session)

        self.assertEqual(features, zone_response.json.return_value["features"])
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual(
            session.get.call_args_list[0].args[0],
            "https://api.weather.gov/points/36.626,-87.466",
        )
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://api.weather.gov/alerts/active?zone=KYZ007",
        )
        self.assertEqual(
            session.get.call_args_list[2].args[0],
            "https://api.weather.gov/alerts/active?zone=KYC047",
        )
        self.assertEqual(
            session.get.call_args_list[3].args[0],
            "https://api.weather.gov/alerts/active?point=36.626,-87.466",
        )
        self.assertIn("36.626,-87.466", weather_monitor.NWS_POINTS_CACHE)
        mock_load_cache.assert_called_once()
        mock_save_cache.assert_called_once()

    @patch("weather_monitor.load_nws_points_cache")
    def test_get_nws_alerts_uses_point_when_zone_metadata_fails(self, mock_load_cache):
        session = Mock()

        points_failure = requests.exceptions.RequestException("points lookup failed")

        point_response = Mock()
        point_response.raise_for_status.return_value = None
        point_response.json.return_value = {
            "features": [{"id": "point-alert-1", "properties": {"event": "Flood Warning"}}]
        }

        session.get.side_effect = [points_failure, point_response]

        features = weather_monitor.get_nws_alerts(36.6260, -87.4660, "Fort Campbell", session=session)

        self.assertEqual(features, point_response.json.return_value["features"])
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(
            session.get.call_args_list[0].args[0],
            "https://api.weather.gov/points/36.626,-87.466",
        )
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://api.weather.gov/alerts/active?point=36.626,-87.466",
        )
        mock_load_cache.assert_called_once()


class TestParseNwsAlerts(unittest.TestCase):
    def test_parse_nws_alerts_returns_stable_id_and_text(self):
        features = [
            {
                "id": "https://api.weather.gov/alerts/NWS-ALERTS-AL12345",
                "properties": {
                    "event": "Tornado Warning for Northern Area",
                    "severity": "Severe",
                    "headline": "A tornado has been spotted.",
                    "effective": "2026-07-19T08:00:00+00:00",
                    "expires": "2026-07-19T09:00:00+00:00",
                    "areaDesc": "Example County",
                },
            }
        ]

        alerts = weather_monitor.parse_nws_alerts(features)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["id"], "NWS-ALERTS-AL12345")
        self.assertEqual(alerts[0]["event_type"], "Tornado Warning for Northern Area")
        self.assertIn("Tornado Warning for Northern Area (Severe)", alerts[0]["text"])
        self.assertEqual(alerts[0]["area"], "Example County")

    def test_parse_nws_alerts_filters_non_critical(self):
        features = [
            {
                "id": "https://api.weather.gov/alerts/non-critical",
                "properties": {
                    "event": "Special Weather Statement",
                    "severity": "Moderate",
                    "areaDesc": "Example County",
                },
            }
        ]

        alerts = weather_monitor.parse_nws_alerts(features)

        self.assertIsNone(alerts)


if __name__ == "__main__":
    unittest.main()
