import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import UTC, datetime

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
    def test_parse_nws_alerts_exact_event_match(self):
        features = [
            {
                "id": "https://api.weather.gov/alerts/NWS-ALERTS-EXACT1",
                "properties": {
                    "event": "Tornado Warning",
                    "severity": "Severe",
                    "areaDesc": "Exact Match County",
                },
            }
        ]

        alerts = weather_monitor.parse_nws_alerts(features)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["event_type"], "Tornado Warning")

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

        self.assertEqual(alerts, [])


class TestDigestAndEscalationHelpers(unittest.TestCase):
    def test_should_send_daily_digest_once_per_day_after_hour(self):
        state = {}
        now = datetime(2026, 7, 25, 11, 5, tzinfo=UTC)

        self.assertTrue(weather_monitor.should_send_daily_digest(state, 11, now))

        state["last_digest_date_utc"] = "2026-07-25"
        self.assertFalse(weather_monitor.should_send_daily_digest(state, 11, now))
        self.assertFalse(
            weather_monitor.should_send_daily_digest(
                {}, 11, datetime(2026, 7, 25, 10, 59, tzinfo=UTC)
            )
        )

    def test_parse_forecast_risks_24h_detects_multiple_categories(self):
        periods = [
            {
                "name": "Tonight",
                "startTime": "2026-07-25T02:00:00+00:00",
                "endTime": "2026-07-25T08:00:00+00:00",
                "shortForecast": "Severe thunderstorms likely with damaging wind and large hail.",
                "detailedForecast": "Heavy rain may cause flash flooding overnight.",
                "windSpeed": "25 mph",
            }
        ]

        risk_summary = weather_monitor.parse_forecast_risks_24h(periods)

        self.assertTrue(risk_summary["has_elevated_risk"])
        self.assertIn("Severe Thunderstorms", risk_summary["top_categories"])
        self.assertIn("Flooding", risk_summary["top_categories"])
        self.assertTrue(risk_summary["evidence"])

    def test_is_immediate_escalation_detects_new_warning(self):
        previous = {
            "events": ["Flood Watch"],
            "warning_events": [],
            "max_severity": weather_monitor.SEVERITY_RANK["moderate"],
        }
        current = {
            "events": ["Flood Watch", "Flood Warning"],
            "warning_events": ["Flood Warning"],
            "max_severity": weather_monitor.SEVERITY_RANK["severe"],
        }

        self.assertTrue(weather_monitor.is_immediate_escalation(previous, current))
        self.assertFalse(weather_monitor.is_immediate_escalation(current, current))


class TestPriorityEngine(unittest.TestCase):
    """Tests for the deterministic executive priority scoring engine."""

    def _empty_risk(self):
        return {'has_elevated_risk': False, 'top_categories': [], 'evidence': [], 'timeframe': ''}

    def _elevated_risk(self, categories=None):
        cats = categories or ['Severe Thunderstorms']
        return {
            'has_elevated_risk': True,
            'top_categories': cats,
            'evidence': ['Evidence line'],
            'timeframe': 'Jul 25',
        }

    # ------------------------------------------------------------------
    # score_location_priority
    # ------------------------------------------------------------------

    def test_no_alerts_no_risk_gives_low_score(self):
        score, band, status, confidence = weather_monitor.score_location_priority(
            [], self._empty_risk(), False
        )
        self.assertEqual(band, 'low')
        self.assertEqual(status, 'normal')
        self.assertLess(score, weather_monitor.PRIORITY_MEDIUM_MIN)
        self.assertLessEqual(confidence, 0.6)

    def test_tornado_warning_severe_escalating_gives_critical(self):
        alerts = [{'event_type': 'Tornado Warning', 'severity': 'Severe'}]
        score, band, status, confidence = weather_monitor.score_location_priority(
            alerts, self._elevated_risk(), True
        )
        self.assertEqual(band, 'critical')
        self.assertEqual(status, 'escalating')
        self.assertGreaterEqual(score, weather_monitor.PRIORITY_CRITICAL_MIN)
        self.assertGreater(confidence, 0.9)

    def test_escalating_flag_sets_status_escalating(self):
        alerts = [{'event_type': 'Flood Watch', 'severity': 'Moderate'}]
        _, _, status, _ = weather_monitor.score_location_priority(
            alerts, self._empty_risk(), True
        )
        self.assertEqual(status, 'escalating')

    def test_active_alerts_no_escalation_status_is_active(self):
        alerts = [{'event_type': 'Flood Warning', 'severity': 'Moderate'}]
        _, _, status, _ = weather_monitor.score_location_priority(
            alerts, self._empty_risk(), False
        )
        self.assertEqual(status, 'active')

    def test_elevated_risk_only_status_is_elevated(self):
        _, _, status, _ = weather_monitor.score_location_priority(
            [], self._elevated_risk(), False
        )
        self.assertEqual(status, 'elevated')

    def test_score_capped_at_100(self):
        alerts = [
            {'event_type': 'Tornado Warning', 'severity': 'Extreme'},
            {'event_type': 'Hurricane Warning', 'severity': 'Extreme'},
        ]
        score, _, _, _ = weather_monitor.score_location_priority(
            alerts, self._elevated_risk(['Severe Thunderstorms', 'Flooding', 'Winter Weather']), True
        )
        self.assertLessEqual(score, 100)

    def test_location_weight_scales_score(self):
        alerts = [{'event_type': 'Wind Advisory', 'severity': 'Minor'}]
        score_default, _, _, _ = weather_monitor.score_location_priority(
            alerts, self._empty_risk(), False, 1.0
        )
        score_double, _, _, _ = weather_monitor.score_location_priority(
            alerts, self._empty_risk(), False, 2.0
        )
        # Doubled weight should yield a higher or equal score (capped at 100)
        self.assertGreaterEqual(score_double, score_default)

    # ------------------------------------------------------------------
    # get_recommended_action
    # ------------------------------------------------------------------

    def test_critical_escalating_action_contains_immediate(self):
        action = weather_monitor.get_recommended_action('critical', 'escalating')
        self.assertIn('IMMEDIATE', action)

    def test_critical_active_action_contains_activate(self):
        action = weather_monitor.get_recommended_action('critical', 'active')
        self.assertIn('Activate', action)

    def test_high_escalating_different_from_high_active(self):
        esc = weather_monitor.get_recommended_action('high', 'escalating')
        act = weather_monitor.get_recommended_action('high', 'active')
        self.assertNotEqual(esc, act)

    def test_low_normal_is_routine(self):
        action = weather_monitor.get_recommended_action('low', 'normal')
        self.assertIn('routine monitoring', action.lower())

    def test_medium_mentions_monitor(self):
        action = weather_monitor.get_recommended_action('medium', 'elevated')
        self.assertIn('monitor', action.lower())


class TestBuildDashboardDigest(unittest.TestCase):
    """Tests for the dashboard JSON assembly function."""

    def _make_loc(self, name, score=0, band='low', status='normal', alerts_count=0, cats=None):
        return {
            'location': name,
            'lat': 36.0,
            'lon': -87.0,
            'country': 'US',
            'status': status,
            'priority_score': score,
            'priority_band': band,
            'confidence': 0.6,
            'risk_categories': cats or [],
            'risk_evidence': [],
            'timeframe': '',
            'active_alerts_count': alerts_count,
            'active_alerts': [],
            'recommended_action': 'No action required; continue routine monitoring.',
            'last_change_utc': '2026-07-25T12:00:00Z',
        }

    def test_summary_counts_are_correct(self):
        locs = [
            self._make_loc('A', score=90, band='critical', status='escalating', alerts_count=1, cats=['Severe Thunderstorms']),
            self._make_loc('B', score=70, band='high', status='active', alerts_count=1),
            self._make_loc('C', score=20, band='low', status='normal'),
        ]
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        delivery = {'digest_email_sent': True, 'digest_email_recipients': 2,
                    'immediate_email_sent': False, 'immediate_email_rows': 0,
                    'immediate_email_recipients': 0}
        changes = {'new_escalations': ['A'], 'new_locations': [], 'resolved_locations': [],
                   'unchanged_locations': ['B', 'C'],
                   'new_escalation_count': 1, 'new_location_count': 0,
                   'resolved_count': 0, 'unchanged_count': 2}

        digest = weather_monitor.build_dashboard_digest(now, locs, delivery, changes)

        summary = digest['summary']
        self.assertEqual(summary['locations_total'], 3)
        self.assertEqual(summary['locations_with_elevated_risk'], 1)
        self.assertEqual(summary['locations_with_active_critical_alerts'], 2)
        self.assertEqual(summary['locations_escalating'], 1)
        self.assertEqual(summary['priority_counts']['critical'], 1)
        self.assertEqual(summary['priority_counts']['high'], 1)
        self.assertEqual(summary['priority_counts']['low'], 1)

    def test_top_locations_sorted_by_score(self):
        locs = [self._make_loc(f'L{i}', score=i * 10) for i in range(12)]
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        digest = weather_monitor.build_dashboard_digest(now, locs, {}, {})
        self.assertEqual(len(digest['top_locations']), 10)
        # Highest score should be first
        self.assertEqual(digest['top_locations'][0]['location'], 'L11')

    def test_run_id_format(self):
        now = datetime(2026, 7, 25, 14, 0, 5, tzinfo=UTC)
        digest = weather_monitor.build_dashboard_digest(now, [], {}, {})
        self.assertTrue(digest['run_id'].startswith('20260725T140005Z_'))
        self.assertEqual(len(digest['run_id']), len('20260725T140005Z_') + 8)

    def test_digest_window_24h_span(self):
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        digest = weather_monitor.build_dashboard_digest(now, [], {}, {})
        self.assertEqual(digest['digest_window']['start_utc'], '2026-07-25T12:00:00Z')
        self.assertEqual(digest['digest_window']['end_utc'], '2026-07-26T12:00:00Z')

    def test_errors_field_present(self):
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        digest = weather_monitor.build_dashboard_digest(now, [], {}, {}, errors=['err1'])
        self.assertEqual(digest['errors'], ['err1'])

    def test_errors_defaults_to_empty_list(self):
        now = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
        digest = weather_monitor.build_dashboard_digest(now, [], {}, {})
        self.assertEqual(digest['errors'], [])


class TestLoadConfig(unittest.TestCase):
    """Tests for the load_config() config-file + env-var merge logic."""

    def _write_config(self, tmp_path, data):
        path = os.path.join(tmp_path, 'config.json')
        with open(path, 'w') as f:
            json.dump(data, f)
        return path

    def test_env_var_overrides_file_credential(self):
        """An env var credential wins over the same key in the config file."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_config(tmp, {'sender_email': 'file@example.com'})
            with patch.dict(os.environ, {'CONFIG_PATH': path, 'SENDER_EMAIL': 'env@example.com'}):
                cfg = weather_monitor.load_config()
        self.assertEqual(cfg['sender_email'], 'env@example.com')

    def test_file_value_used_when_no_env_var(self):
        """A config-file value is kept when the corresponding env var is absent."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_config(tmp, {'sender_email': 'file@example.com'})
            env = {k: v for k, v in os.environ.items()
                   if k not in ('SENDER_EMAIL', 'CONFIG_PATH')}
            env['CONFIG_PATH'] = path
            with patch.dict(os.environ, env, clear=True):
                cfg = weather_monitor.load_config()
        self.assertEqual(cfg['sender_email'], 'file@example.com')

    def test_recipient_emails_parsed_from_env(self):
        """RECIPIENT_EMAILS env var is split on commas and whitespace-stripped."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_config(tmp, {})
            with patch.dict(os.environ, {
                'CONFIG_PATH': path,
                'RECIPIENT_EMAILS': 'a@example.com, b@example.com',
            }):
                cfg = weather_monitor.load_config()
        self.assertEqual(cfg['recipient_emails'], ['a@example.com', 'b@example.com'])

    def test_default_locations_used_when_config_empty(self):
        """Built-in default locations are returned when neither the file nor env provides any."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_config(tmp, {})
            env = {k: v for k, v in os.environ.items()
                   if k not in ('CONFIG_PATH',)}
            env['CONFIG_PATH'] = path
            with patch.dict(os.environ, env, clear=True):
                cfg = weather_monitor.load_config()
        self.assertIsInstance(cfg['locations'], list)
        self.assertGreater(len(cfg['locations']), 0)

    def test_missing_config_file_falls_back_to_env_and_defaults(self):
        """A missing config file is handled gracefully; env vars and defaults still apply."""
        with patch.dict(os.environ, {
            'CONFIG_PATH': '/nonexistent/path/config.json',
            'SENDER_EMAIL': 'env@example.com',
        }):
            cfg = weather_monitor.load_config()
        self.assertEqual(cfg['sender_email'], 'env@example.com')
        self.assertIsInstance(cfg.get('locations'), list)


class TestIsStaleAlert(unittest.TestCase):
    """Tests for the _is_stale_alert() helper."""

    def _row(self, message_type='', description='', summary='', text=''):
        return {
            'message_type': message_type,
            'description': description,
            'summary': summary,
            'text': text,
        }

    def test_cancel_message_type_is_stale(self):
        self.assertTrue(weather_monitor._is_stale_alert(self._row(message_type='Cancel')))

    def test_cancel_case_insensitive(self):
        self.assertTrue(weather_monitor._is_stale_alert(self._row(message_type='CANCEL')))
        self.assertTrue(weather_monitor._is_stale_alert(self._row(message_type='cancel')))

    def test_superseded_in_description_is_stale(self):
        self.assertTrue(weather_monitor._is_stale_alert(
            self._row(description='This statement has been superseded.')))

    def test_replaced_in_summary_is_stale(self):
        self.assertTrue(weather_monitor._is_stale_alert(
            self._row(summary='Alert replaced by newer issuance.')))

    def test_canceled_in_text_is_stale(self):
        self.assertTrue(weather_monitor._is_stale_alert(
            self._row(text='Warning canceled due to no further threat.')))

    def test_cancelled_british_spelling_is_stale(self):
        self.assertTrue(weather_monitor._is_stale_alert(
            self._row(description='Warning has been cancelled.')))

    def test_normal_alert_is_not_stale(self):
        self.assertFalse(weather_monitor._is_stale_alert(
            self._row(message_type='Alert', text='Tornado Warning (Severe)')))

    def test_empty_row_is_not_stale(self):
        self.assertFalse(weather_monitor._is_stale_alert({}))


class TestAggregateEscalationAlerts(unittest.TestCase):
    """Tests for the aggregate_escalation_alerts() function."""

    def _row(self, location='LOC A', event_type='Tornado Warning', severity='Severe',
             effective='2026-07-25T10:00:00+00:00', expires='2026-07-25T11:00:00+00:00',
             issue_time='', message_type='Alert', description='', summary='', text=''):
        return {
            'location': location,
            'event_type': event_type,
            'severity': severity,
            'effective': effective,
            'expires': expires,
            'issue_time': issue_time,
            'message_type': message_type,
            'description': description,
            'summary': summary,
            'text': text,
        }

    # ------------------------------------------------------------------
    # Basic grouping and [NEW] tag
    # ------------------------------------------------------------------

    def test_single_alert_tagged_new(self):
        rows = [self._row()]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['threats']), 1)
        self.assertEqual(result[0]['threats'][0]['tag'], '[NEW]')

    def test_single_alert_preserves_fields(self):
        rows = [self._row(event_type='Flood Warning', severity='Moderate')]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        threat = result[0]['threats'][0]
        self.assertEqual(threat['event_type'], 'Flood Warning')
        self.assertEqual(threat['severity'], 'Moderate')

    def test_two_different_events_same_location_both_new(self):
        rows = [
            self._row(event_type='Tornado Warning', severity='Severe'),
            self._row(event_type='Flood Warning', severity='Moderate'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['total_threats'], 2)
        tags = {t['tag'] for t in result[0]['threats']}
        self.assertEqual(tags, {'[NEW]'})

    # ------------------------------------------------------------------
    # [UPDATED] / [EXTENDED] collapse logic
    # ------------------------------------------------------------------

    def test_same_event_two_records_same_expiry_tagged_updated(self):
        rows = [
            self._row(issue_time='2026-07-25T09:00:00+00:00',
                      expires='2026-07-25T11:00:00+00:00'),
            self._row(issue_time='2026-07-25T10:00:00+00:00',
                      expires='2026-07-25T11:00:00+00:00'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(result[0]['total_threats'], 1)
        self.assertEqual(result[0]['threats'][0]['tag'], '[UPDATED]')

    def test_same_event_two_records_later_expiry_tagged_extended(self):
        rows = [
            self._row(issue_time='2026-07-25T09:00:00+00:00',
                      expires='2026-07-25T11:00:00+00:00'),
            self._row(issue_time='2026-07-25T10:00:00+00:00',
                      expires='2026-07-25T13:00:00+00:00'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        threat = result[0]['threats'][0]
        self.assertEqual(threat['tag'], '[EXTENDED]')
        self.assertIsNotNone(threat['note'])
        self.assertIn('→', threat['note'])

    def test_extended_note_contains_original_and_new_expiry(self):
        rows = [
            self._row(issue_time='2026-07-25T09:00:00+00:00',
                      expires='2026-07-25T11:00:00+00:00'),
            self._row(issue_time='2026-07-25T10:00:00+00:00',
                      expires='2026-07-25T15:00:00+00:00'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        note = result[0]['threats'][0]['note']
        self.assertIn('2026-07-25T11:00:00+00:00', note)
        self.assertIn('2026-07-25T15:00:00+00:00', note)

    # ------------------------------------------------------------------
    # Stale/cancel filtering
    # ------------------------------------------------------------------

    def test_canceled_alert_excluded(self):
        rows = [self._row(message_type='Cancel')]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(result, [])

    def test_only_stale_alerts_location_excluded(self):
        rows = [
            self._row(message_type='Cancel'),
            self._row(description='This has been superseded.'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(result, [])

    def test_mixed_stale_and_active_keeps_active(self):
        rows = [
            self._row(event_type='Tornado Warning', message_type='Cancel'),
            self._row(event_type='Flood Warning', message_type='Alert'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['threats'][0]['event_type'], 'Flood Warning')

    # ------------------------------------------------------------------
    # Severity sorting within a location
    # ------------------------------------------------------------------

    def test_threats_sorted_by_severity_descending(self):
        rows = [
            self._row(event_type='Wind Advisory', severity='Minor'),
            self._row(event_type='Tornado Warning', severity='Severe'),
            self._row(event_type='Flood Warning', severity='Moderate'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        severities = [t['severity'] for t in result[0]['threats']]
        self.assertEqual(severities, ['Severe', 'Moderate', 'Minor'])

    # ------------------------------------------------------------------
    # Location sorting
    # ------------------------------------------------------------------

    def test_locations_sorted_by_threat_count_descending(self):
        rows = [
            self._row(location='LOC A', event_type='Tornado Warning', severity='Severe'),
            self._row(location='LOC B', event_type='Tornado Warning', severity='Severe'),
            self._row(location='LOC B', event_type='Flood Warning', severity='Moderate'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(result[0]['location'], 'LOC B')
        self.assertEqual(result[1]['location'], 'LOC A')

    def test_location_tiebreak_by_max_severity(self):
        rows = [
            self._row(location='LOC A', event_type='Tornado Warning', severity='Moderate'),
            self._row(location='LOC B', event_type='Tornado Warning', severity='Severe'),
        ]
        result = weather_monitor.aggregate_escalation_alerts(rows)
        self.assertEqual(result[0]['location'], 'LOC B')

    def test_empty_input_returns_empty(self):
        self.assertEqual(weather_monitor.aggregate_escalation_alerts([]), [])

    # ------------------------------------------------------------------
    # parse_nws_alerts produces new fields
    # ------------------------------------------------------------------

    def test_parse_nws_alerts_includes_message_type_and_issue_time(self):
        features = [
            {
                'id': 'https://api.weather.gov/alerts/NWS-TEST-1',
                'properties': {
                    'event': 'Tornado Warning',
                    'severity': 'Severe',
                    'areaDesc': 'Test County',
                    'messageType': 'Update',
                    'sent': '2026-07-25T10:00:00+00:00',
                    'description': 'A tornado warning is in effect.',
                    'summary': '',
                },
            }
        ]
        alerts = weather_monitor.parse_nws_alerts(features)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['message_type'], 'Update')
        self.assertEqual(alerts[0]['issue_time'], '2026-07-25T10:00:00+00:00')
        self.assertEqual(alerts[0]['description'], 'A tornado warning is in effect.')


if __name__ == "__main__":
    unittest.main()
