import unittest
from unittest.mock import Mock, patch

import requests

import weather_monitor


class GetNwsAlertsTests(unittest.TestCase):
    def setUp(self):
        weather_monitor.NWS_POINTS_CACHE = {}

    @patch("weather_monitor.load_nws_points_cache")
    def test_get_nws_alerts_uses_point_lookup_first(self, mock_load_cache):
        session = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "features": [{"properties": {"event": "Severe Thunderstorm Warning"}}]
        }
        session.get.return_value = response

        features = weather_monitor.get_nws_alerts(36.6260, -87.4660, "Fort Campbell", session=session)

        self.assertEqual(features, response.json.return_value["features"])
        session.get.assert_called_once_with(
            "https://api.weather.gov/alerts/active?point=36.626,-87.466",
            timeout=10,
        )
        mock_load_cache.assert_called_once()

    @patch("weather_monitor.load_nws_points_cache")
    @patch("weather_monitor.save_nws_points_cache")
    def test_get_nws_alerts_falls_back_to_legacy_points_lookup(self, mock_save_cache, mock_load_cache):
        session = Mock()

        point_failure = requests.exceptions.RequestException("point lookup failed")

        points_response = Mock()
        points_response.raise_for_status.return_value = None
        points_response.json.return_value = {
            "properties": {"alerts": "https://api.weather.gov/alerts/active/zone/KYZ007"}
        }

        alerts_response = Mock()
        alerts_response.raise_for_status.return_value = None
        alerts_response.json.return_value = {
            "features": [{"properties": {"event": "Flood Warning"}}]
        }

        session.get.side_effect = [point_failure, points_response, alerts_response]

        features = weather_monitor.get_nws_alerts(36.6260, -87.4660, "Fort Campbell", session=session)

        self.assertEqual(features, alerts_response.json.return_value["features"])
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual(
            session.get.call_args_list[0].args[0],
            "https://api.weather.gov/alerts/active?point=36.626,-87.466",
        )
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://api.weather.gov/points/36.626,-87.466",
        )
        self.assertEqual(
            session.get.call_args_list[2].args[0],
            "https://api.weather.gov/alerts/active/zone/KYZ007",
        )
        self.assertIn("36.626,-87.466", weather_monitor.NWS_POINTS_CACHE)
        mock_load_cache.assert_called_once()
        mock_save_cache.assert_called_once()


if __name__ == "__main__":
    unittest.main()
