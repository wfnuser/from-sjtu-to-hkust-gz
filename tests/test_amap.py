import io
import json
from pathlib import Path
import ssl
import tempfile
import traceback
import unittest
from unittest.mock import patch

from route_planner.amap import AmapClient, AmapError, load_amap_key
from route_planner.models import Coordinate, RoadClass


ORIGIN = Coordinate(121.436015, 31.025787)
DESTINATION = Coordinate(121.442902, 31.018286)
FIXTURES = Path(__file__).parent / "fixtures"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AmapClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def fixture_client(self, name: str, *, key="sanitized-test-key", min_interval_s=0):
        cache_dir = tempfile.TemporaryDirectory()
        self.addCleanup(cache_dir.cleanup)
        client = AmapClient(key, Path(cache_dir.name), min_interval_s=min_interval_s)
        payload = (FIXTURES / name).read_bytes()
        client._urlopen = lambda request, timeout=30, **kwargs: _Response(payload)
        return client

    def test_load_amap_key_reads_named_value_without_retaining_env_syntax(self):
        path = Path(self.tmp.name) / ".env.local"
        path.write_text("# local only\nAMAP_KEY=secret-123\n", encoding="utf-8")

        self.assertEqual(load_amap_key(path), "secret-123")

    def test_load_amap_key_supports_configured_web_service_key_name(self):
        path = Path(self.tmp.name) / ".env.local"
        path.write_text("AMAP_WEB_SERVICE_KEY=secret-123\n", encoding="utf-8")

        self.assertEqual(load_amap_key(path), "secret-123")

    def test_cache_key_is_independent_of_client_or_parameter_secret(self):
        params = {"origin": "1,2", "key": "parameter-secret"}
        key = AmapClient("secret-123", Path(self.tmp.name), min_interval_s=0).cache_key(
            "/v5/direction/electrobike", params
        )
        other_key = AmapClient("other-secret", Path(self.tmp.name), min_interval_s=0).cache_key(
            "/v5/direction/electrobike", {"origin": "1,2"}
        )

        self.assertNotIn("secret-123", key)
        self.assertNotIn("parameter-secret", key)
        self.assertEqual(key, other_key)

    def test_electrobike_parses_all_alternatives_and_steps(self):
        client = self.fixture_client("electrobike-ok.json")

        routes = client.electrobike(Coordinate(121.43, 31.02), Coordinate(121.44, 31.01))

        self.assertEqual(len(routes), 2)
        self.assertTrue(routes[0].steps[0].polyline_gcj)
        self.assertEqual(routes[0].steps[1].road_class, RoadClass.COUNTY)
        self.assertEqual(routes[0].steps[0].risk_tags, frozenset())

    def test_electrobike_requests_polyline_and_three_alternatives(self):
        client = self.fixture_client("electrobike-ok.json")
        captured = []
        original = client._urlopen
        client._urlopen = lambda request, timeout=30, **kwargs: (
            captured.append(request.full_url), original(request, timeout, **kwargs)
        )[1]

        client.electrobike(ORIGIN, DESTINATION)

        self.assertIn("show_fields=polyline", captured[0])
        self.assertIn("alternative_route=3", captured[0])
        self.assertIn("key=sanitized-test-key", captured[0])

    def test_geocode_parses_candidates(self):
        candidates = self.fixture_client("geocode-ok.json").geocode("上海交通大学闵行校区", "上海")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "上海交通大学闵行校区")
        self.assertEqual(candidates[0].formatted_address, "上海市东川路")
        self.assertEqual(candidates[0].district, "")
        self.assertEqual(candidates[0].location_gcj, ORIGIN)

    def test_non_ok_infocode_raises_without_logging_key_or_cache_file(self):
        client = self.fixture_client("invalid-key.json")
        with self.assertRaisesRegex(AmapError, "10001") as caught:
            client.electrobike(ORIGIN, DESTINATION)

        self.assertNotIn("sanitized-test-key", str(caught.exception))
        self.assertEqual(list(client.cache_dir.glob("*.json")), [])

    def test_successful_cache_hit_does_not_start_another_network_request(self):
        client = self.fixture_client("electrobike-ok.json")
        calls = 0
        original = client._urlopen

        def counted_urlopen(request, timeout=30, **kwargs):
            nonlocal calls
            calls += 1
            return original(request, timeout, **kwargs)

        client._urlopen = counted_urlopen
        client.electrobike(ORIGIN, DESTINATION)
        client.electrobike(ORIGIN, DESTINATION)

        self.assertEqual(calls, 1)

    def test_transport_error_has_no_secret_in_exception_chain_or_traceback(self):
        secret = "secret-123"
        client = AmapClient(secret, Path(self.tmp.name), min_interval_s=0)
        client._urlopen = lambda request, timeout=30, **kwargs: (_ for _ in ()).throw(
            OSError(f"request failed for {request.full_url}")
        )

        with self.assertRaises(AmapError) as caught:
            client.electrobike(ORIGIN, DESTINATION)

        chain = []
        current = caught.exception
        while current is not None:
            chain.append(str(current))
            current = current.__cause__ or current.__context__
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn(secret, "\n".join(chain))
        self.assertNotIn(secret, rendered)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_throttle_sleeps_exact_remaining_interval_between_starts(self):
        client = AmapClient("sanitized-test-key", Path(self.tmp.name), min_interval_s=0.34)
        with patch("route_planner.amap.time.monotonic", side_effect=[10.0, 10.1, 10.34]), patch(
            "route_planner.amap.time.sleep"
        ) as sleep:
            client._throttle()
            client._throttle()

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.24)
        self.assertEqual(client._last_start_monotonic, 10.34)

    def test_tls_context_verifies_certificates_and_hostnames(self):
        client = AmapClient("sanitized-test-key", Path(self.tmp.name), min_interval_s=0)

        self.assertEqual(client._ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(client._ssl_context.check_hostname)


class AmapLiveSmokeTest(unittest.TestCase):
    @unittest.skipUnless(Path(".env.local").exists(), ".env.local is not configured")
    def test_configured_key_returns_electrobike_candidates(self):
        key = load_amap_key(Path(".env.local"))
        with tempfile.TemporaryDirectory() as cache_dir:
            routes = AmapClient(key, Path(cache_dir)).electrobike(ORIGIN, DESTINATION)

        self.assertIn(len(routes), (2, 3))
        self.assertTrue(routes[0].steps[0].polyline_gcj)


if __name__ == "__main__":
    unittest.main()
