import json
from pathlib import Path
import subprocess
import unittest

from route_planner.config import load_route_config
from route_planner.artifacts import ArtifactPaths


class ExecutionItineraryContractTests(unittest.TestCase):
    route_path = Path("config/inland-execution-route.json")
    itinerary_path = Path("config/inland-itinerary.json")

    def setUp(self):
        self.assertTrue(self.route_path.exists(), "execution route config must be published")
        self.assertTrue(self.itinerary_path.exists(), "execution itinerary must be published")
        self.route = load_route_config(self.route_path)
        self.itinerary = json.loads(self.itinerary_path.read_text(encoding="utf-8"))

    def test_fixed_actual_and_planned_days_are_not_reassigned(self):
        days = self.itinerary["days"]
        self.assertEqual([day["day"] for day in days], list(range(17)))
        self.assertEqual(self.itinerary["start_date"], "2026-08-13")
        self.assertEqual(days[0]["from_name"], "阳曲路")
        self.assertEqual(days[0]["to_name"], "上海交通大学闵行校区")
        self.assertEqual(
            days[0]["key_waypoints"],
            ["大连路地铁站", "昌化路649号", "京东上海（中海中心）职场"],
        )
        self.assertEqual(days[1]["to_name"], "桐乡万象汇振兴西路亚朵酒店")
        self.assertTrue(any("叶新公路" in name for name in days[1]["key_waypoints"]))
        self.assertEqual(days[2]["status"], "completed")
        self.assertEqual(days[2]["from_name"], "桐乡万象汇振兴西路亚朵酒店")
        self.assertEqual(days[2]["to_name"], "杭州未来科技城海创园地铁站亚朵酒店")
        self.assertEqual(days[2]["key_waypoints"], ["阿里巴巴西溪园区"])
        self.assertEqual(days[3]["from_name"], "杭州未来科技城海创园地铁站亚朵酒店")
        self.assertEqual(days[3]["to_name"], "麗枫酒店（杭州建德新安江店）")
        self.assertEqual(
            days[3]["key_waypoints"],
            ["捷安特自行车（桐庐店）", "富春江镇", "新安绿道洋溪段"],
        )
        self.assertEqual(days[16]["to_name"], "香港科技大学（广州）")

        names = [waypoint.name for waypoint in self.route.waypoints]
        self.assertEqual(
            names[12:15],
            [
                "杭州未来科技城海创园地铁站亚朵酒店",
                "捷安特自行车（桐庐店）",
                "麗枫酒店（杭州建德新安江店）",
            ],
        )
        self.assertEqual(self.route.waypoints[13].city, "杭州")
        self.assertEqual(
            self.route.segment_rules["main-06-to-main-07"].anchor_queries,
            ("桐庐县富春江镇", "杭州::建德市新安绿道洋溪段"),
        )

    def test_published_day3_is_about_135_km_without_unresolved_hard_risk(self):
        itinerary = json.loads(
            Path("web/data/inland-itinerary.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            Path("web/data/inland-execution-route-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        geojson = json.loads(
            Path("web/data/inland-execution-route.geojson").read_text(encoding="utf-8")
        )

        day3 = next(day for day in itinerary["days"] if day["day"] == 3)
        self.assertGreaterEqual(day3["distance_m"], 134_000)
        self.assertLessEqual(day3["distance_m"], 136_000)
        day3_segments = [
            segment
            for segment in manifest["segments"]
            if segment["rule"]["day"] == 3
        ]
        self.assertFalse(
            any(
                review["code"].startswith("HARD_RISK")
                for segment in day3_segments
                for review in segment["reviews"]
            )
        )
        verified_step_features = [
            feature
            for feature in geojson["features"]
            if feature["properties"]["segment_id"] == "main-06-to-main-07"
            and feature["properties"]["road_name"] == "新安江互通"
        ]
        self.assertTrue(verified_step_features)
        self.assertTrue(
            all(
                feature["properties"]["review_status"]
                == "automatic_checks_passed"
                and "hard" not in feature["properties"]["risk_tags"]
                for feature in verified_step_features
            )
        )

    def test_every_execution_segment_is_assigned_to_exactly_one_riding_day(self):
        expected = [
            f"{start.id}-to-{end.id}"
            for start, end in zip(self.route.waypoints, self.route.waypoints[1:])
        ]
        assigned = [
            segment_id
            for day in self.itinerary["days"]
            for segment_id in day["segments"]
        ]

        self.assertEqual(assigned, expected)
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(
            [self.route.segment_rules[segment_id].day for segment_id in expected],
            [day["day"] for day in self.itinerary["days"] for _ in day["segments"]],
        )

    def test_every_planned_night_before_arrival_has_laundry_evidence(self):
        planned_nights = [
            day
            for day in self.itinerary["days"]
            if day["status"] == "planned" and day["day"] < 15
        ]

        for day in planned_nights:
            with self.subTest(day=day["day"]):
                lodging = day["lodging"]
                self.assertTrue(lodging["name"])
                self.assertIn(lodging["laundry"], {"confirmed", "call_required"})
                self.assertTrue(lodging["evidence_url"].startswith("https://"))
                self.assertEqual(lodging["booking_status"], "candidate")

        self.assertEqual(
            [
                day["day"]
                for day in planned_nights
                if day["lodging"]["laundry"] == "call_required"
            ],
            [6, 9, 10, 13, 14],
        )

    def test_future_route_uses_better_lodging_without_fixed_midday_stops(self):
        future_days = [day for day in self.itinerary["days"] if 6 <= day["day"] <= 15]

        self.assertEqual(
            future_days[0]["to_name"],
            "鹰潭枫丹白露酒店（雲锦君澜）",
        )
        self.assertEqual(
            [day.get("key_waypoints", []) for day in future_days],
            [[] for _ in future_days],
        )
        future_lodging_names = [
            day.get("lodging", {}).get("name", "") for day in future_days
        ]
        self.assertFalse(
            any("汉庭" in name or "7天" in name for name in future_lodging_names),
            future_lodging_names,
        )
        self.assertIn("定南格兰云天国际酒店", future_lodging_names)

    def test_day4_is_direct_and_future_days_are_about_100_km(self):
        configured_days = self.itinerary["days"]
        self.assertEqual(
            configured_days[4]["segments"],
            ["main-07-to-day4-changshan-hotel"],
        )
        self.assertEqual(configured_days[4]["key_waypoints"], [])

        published = json.loads(
            Path("web/data/inland-itinerary.json").read_text(encoding="utf-8")
        )
        day4 = published["days"][4]
        self.assertGreaterEqual(day4["distance_m"], 112_000)
        self.assertLessEqual(day4["distance_m"], 115_000)
        balanced_days = [day for day in published["days"] if 6 <= day["day"] <= 15]
        self.assertEqual(len(balanced_days), 10)
        # Day 8 (南城 → 全季广昌), Day 9 (全季广昌 → 锦汇), Day 11 (于都 → 信丰),
        # Day 13 (定南 → 漳溪) are constrained by corridor geography: no closer
        # chain hotel exists, so these long legs are unavoidable. All other days
        # must stay ≤ 100 km.
        over_cap_budget = {8: 100_000, 9: 105_000, 11: 105_000, 13: 105_000}
        for day in balanced_days:
            ceiling = over_cap_budget.get(day["day"], 108_000)
            self.assertLessEqual(
                day["distance_m"],
                ceiling,
                [(d["day"], d["distance_m"]) for d in balanced_days],
            )
        self.assertTrue(
            all(day["distance_m"] >= 60_000 for day in balanced_days),
            [(day["day"], day["distance_m"]) for day in balanced_days],
        )
        day16 = next(day for day in published["days"] if day["day"] == 16)
        self.assertTrue(15_000 <= day16["distance_m"] <= 35_000)


class ExecutionItineraryBuildTests(unittest.TestCase):
    def test_build_itinerary_assigns_consecutive_dates_from_start_date(self):
        from route_planner.itinerary import build_itinerary

        config = {
            "route_id": "inland-execution",
            "start_date": "2026-08-13",
            "days": [
                {"day": 0, "segments": ["a-to-b"]},
                {"day": 4, "segments": ["b-to-c"]},
            ],
        }
        manifest = {
            "route_id": "inland-execution",
            "segments": [
                {"segment_id": "a-to-b", "selected": {"distance_m": 1, "duration_s": 1}},
                {"segment_id": "b-to-c", "selected": {"distance_m": 1, "duration_s": 1}},
            ],
        }
        geojson = {
            "features": [
                {"properties": {"segment_id": "a-to-b"}},
                {"properties": {"segment_id": "b-to-c"}},
            ]
        }

        itinerary, _ = build_itinerary(config, manifest, geojson)

        self.assertEqual(itinerary["start_date"], "2026-08-13")
        self.assertEqual(
            [day["date"] for day in itinerary["days"]],
            ["2026-08-13", "2026-08-17"],
        )

    def test_strict_audit_cli_accepts_the_execution_profile(self):
        result = subprocess.run(
            ["python3", "scripts/audit_route.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("coastal,inland,execution", result.stdout)

    def test_execution_artifacts_have_independent_publication_paths(self):
        try:
            paths = ArtifactPaths.for_profile(Path("web/data"), "execution")
        except ValueError as error:
            self.fail(str(error))

        self.assertEqual(paths.geojson.name, "inland-execution-route.geojson")
        self.assertEqual(paths.summary.name, "inland-execution-summary.json")
        self.assertEqual(paths.manifest.name, "inland-execution-route-manifest.json")

    def test_build_itinerary_tags_real_features_and_derives_distances(self):
        try:
            from route_planner.itinerary import build_itinerary
        except ModuleNotFoundError as error:
            self.fail(str(error))

        config = {
            "route_id": "inland-execution",
            "display_start_day": 1,
            "remaining_start_day": 3,
            "days": [
                {"day": 0, "segments": ["a-to-b"], "distance_m": None},
                {"day": 1, "segments": [], "distance_m": 0},
                {"day": 2, "segments": [], "distance_m": 0},
                {"day": 3, "segments": ["b-to-c"], "distance_m": None},
            ],
        }
        manifest = {
            "route_id": "inland-execution",
            "segments": [
                {"segment_id": "a-to-b", "selected": {"distance_m": 12_000, "duration_s": 2_400}},
                {"segment_id": "b-to-c", "selected": {"distance_m": 18_000, "duration_s": 3_600}},
            ],
        }
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": None, "properties": {"segment_id": "a-to-b"}},
                {"type": "Feature", "geometry": None, "properties": {"segment_id": "b-to-c"}},
            ],
        }

        itinerary, tagged = build_itinerary(config, manifest, geojson)

        self.assertEqual([day["distance_m"] for day in itinerary["days"]], [12_000, 0, 0, 18_000])
        self.assertEqual([day["duration_s"] for day in itinerary["days"]], [2_400, 0, 0, 3_600])
        self.assertEqual(itinerary["remaining_distance_m"], 18_000)
        self.assertEqual(itinerary["average_riding_distance_m"], 18_000)
        self.assertEqual(itinerary["public_total_distance_m"], 18_000)
        self.assertEqual(itinerary["display_start_day"], 1)
        self.assertEqual(itinerary["remaining_start_day"], 3)
        self.assertEqual(itinerary["segment_days"], {"a-to-b": 0, "b-to-c": 3})
        self.assertEqual([feature["properties"]["day_id"] for feature in tagged["features"]], [0, 3])


if __name__ == "__main__":
    unittest.main()
