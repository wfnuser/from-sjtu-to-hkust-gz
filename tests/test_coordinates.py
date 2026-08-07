import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from route_planner.coordinates import gcj02_to_wgs84, parse_polyline, resolve_waypoints
from route_planner.models import Coordinate, GeocodeCandidate, RouteConfig, Waypoint


class CoordinateTests(unittest.TestCase):
    def test_resolve_pois_cli_runs_from_the_documented_project_root(self):
        result = subprocess.run(
            [sys.executable, "scripts/resolve_pois.py", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--config", result.stdout)

    def test_resolution_report_includes_poi_id_provenance(self):
        from scripts.resolve_pois import _resolution_payload

        candidate = GeocodeCandidate(
            "香港科技大学(广州)",
            "广东省广州市南沙区笃学路1号",
            "南沙区",
            Coordinate(113.484507, 22.889043),
            "B0IGJURJOJ",
        )
        report = resolve_waypoints(
            RouteConfig(
                "test",
                1.15,
                (Waypoint("end", "香港科技大学（广州）", "广州", "香港科技大学（广州）"),),
                (),
                {},
                {},
            ),
            _GeocodeClient({("香港科技大学（广州）", "广州"): (candidate,)}),
        )

        payload = _resolution_payload(report)

        self.assertEqual(payload["resolutions"][0]["candidates"][0]["poi_id"], "B0IGJURJOJ")

    def test_resolver_rerun_preserves_optional_checkin_provenance(self):
        from scripts.resolve_pois import _write_report

        report = resolve_waypoints(
            RouteConfig(
                "test", 1.15,
                (Waypoint("start", "起点", "上海", "起点"),),
                (), {}, {},
            ),
            _GeocodeClient(
                {
                    ("起点", "上海"): (
                        GeocodeCandidate(
                            "起点", "上海市起点", "静安区", Coordinate(121.4, 31.2), "POI-MAIN"
                        ),
                    )
                }
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "poi-resolutions.json"
            checkins = [{"query": "阳曲路住处", "city": "上海", "candidates": []}]
            path.write_text(
                json.dumps(
                    {
                        "resolutions": [],
                        "unresolved_queries": [],
                        "checkin_resolutions": checkins,
                        "unresolved_checkin_queries": ["阳曲路住处"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            _write_report(path, report)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["checkin_resolutions"], checkins)
            self.assertEqual(payload["unresolved_checkin_queries"], ["阳曲路住处"])

    def test_parse_polyline_preserves_order(self):
        self.assertEqual(
            parse_polyline("121.1,31.1;121.2,31.2"),
            (Coordinate(121.1, 31.1), Coordinate(121.2, 31.2)),
        )

    def test_gcj_conversion_is_small_but_nonzero_in_shanghai(self):
        source = Coordinate(121.436015, 31.025787)

        converted = gcj02_to_wgs84(source)

        self.assertGreater(abs(source.lon - converted.lon), 0.001)
        self.assertLess(abs(source.lon - converted.lon), 0.02)

    def test_resolve_waypoints_selects_only_one_exact_city_candidate(self):
        config = RouteConfig(
            "test",
            1.15,
            (
                Waypoint("start", "上海交通大学闵行校区", "上海", "上海交通大学闵行校区"),
                Waypoint("end", "香港科技大学（广州）", "广州", "香港科技大学（广州）"),
            ),
            (),
            {},
            {},
        )
        client = _GeocodeClient(
            {
                ("上海交通大学闵行校区", "上海"): (
                    GeocodeCandidate(
                        "上海交通大学闵行校区",
                        "上海市闵行区东川路",
                        "闵行区",
                        Coordinate(121.436015, 31.025787),
                    ),
                ),
                ("香港科技大学（广州）", "广州"): (
                    GeocodeCandidate(
                        "香港科技大学（广州）",
                        "广东省广州市番禺区",
                        "番禺区",
                        Coordinate(113.0, 23.0),
                    ),
                    GeocodeCandidate(
                        "香港科技大学（广州）",
                        "广东省广州市南沙区",
                        "南沙区",
                        Coordinate(113.1, 23.1),
                    ),
                ),
            }
        )

        report = resolve_waypoints(config, client)

        self.assertEqual(report.resolutions[0].selected, report.resolutions[0].candidates[0])
        self.assertIsNone(report.resolutions[1].selected)
        self.assertEqual(report.unresolved_queries, ("香港科技大学（广州）",))

    def test_resolve_waypoints_rejects_city_text_inside_an_out_of_city_address(self):
        config = RouteConfig(
            "test",
            1.15,
            (Waypoint("poi", "上海地点", "上海", "上海地点"),),
            (),
            {},
            {},
        )
        client = _GeocodeClient(
            {
                ("上海地点", "上海"): (
                    GeocodeCandidate(
                        "上海地点",
                        "江苏省苏州市上海市路",
                        "姑苏区",
                        Coordinate(120.6, 31.3),
                    ),
                ),
            }
        )

        report = resolve_waypoints(config, client)

        self.assertIsNone(report.resolutions[0].selected)
        self.assertEqual(report.unresolved_queries, ("上海地点",))


class _GeocodeClient:
    def __init__(self, candidates):
        self._candidates = candidates

    def geocode(self, query, city):
        return self._candidates[(query, city)]


if __name__ == "__main__":
    unittest.main()
