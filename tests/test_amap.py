import io
import json
from pathlib import Path
import tempfile
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


def fixture_client(name: str) -> AmapClient:
    client = AmapClient("sanitized-test-key", Path(tempfile.mkdtemp()), min_interval_s=0)
    payload = (FIXTURES / name).read_bytes()
    client._urlopen = lambda request, timeout=30: _Response(payload)
    return client


class AmapClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_amap_key_reads_named_value_without_retaining_env_syntax(self):
        path = Path(self.tmp.name) / ".env.local"
        path.write_text("# local only\nAMAP_KEY=secret-123\n", encoding="utf-8")

        self.assertEqual(load_amap_key(path), "secret-123")

    def test_load_amap_key_supports_configured_web_service_key_name(self):
        path = Path(self.tmp.name) / ".env.local"
        path.write_text("AMAP_WEB_SERVICE_KEY=secret-123\n", encoding="utf-8")

        self.assertEqual(load_amap_key(path), "secret-123")

    def test_cache_key_never_contains_secret(self):
        client = AmapClient("secret-123", Path(self.tmp.name), min_interval_s=0)
        key = client.cache_key("/v5/direction/electrobike", {"origin": "1,2", "key": "secret-123"})

        self.assertNotIn("secret-123", key)

    def test_electrobike_parses_all_alternatives_and_steps(self):
        client = fixture_client("electrobike-ok.json")

        routes = client.electrobike(Coordinate(121.43, 31.02), Coordinate(121.44, 31.01))

        self.assertEqual(len(routes), 2)
        self.assertTrue(routes[0].steps[0].polyline_gcj)
        self.assertEqual(routes[0].steps[1].road_class, RoadClass.COUNTY)
        self.assertEqual(routes[0].steps[0].risk_tags, frozenset())

    def test_electrobike_requests_polyline_and_three_alternatives(self):
        client = fixture_client("electrobike-ok.json")
        captured = []
        original = client._urlopen
        client._urlopen = lambda request, timeout=30: (captured.append(request.full_url), original(request, timeout))[1]

        client.electrobike(ORIGIN, DESTINATION)

        self.assertIn("show_fields=polyline", captured[0])
        self.assertIn("alternative_route=3", captured[0])
        self.assertIn("key=sanitized-test-key", captured[0])

    def test_geocode_parses_candidates(self):
        candidates = fixture_client("geocode-ok.json").geocode("上海交通大学闵行校区", "上海")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].location_gcj, ORIGIN)

    def test_non_ok_infocode_raises_without_logging_key(self):
        with self.assertRaisesRegex(AmapError, "10001") as caught:
            fixture_client("invalid-key.json").electrobike(ORIGIN, DESTINATION)

        self.assertNotIn("sanitized-test-key", str(caught.exception))


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
