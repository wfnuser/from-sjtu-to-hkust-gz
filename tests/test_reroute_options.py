import unittest

from route_planner.reroute_options import RerouteOption, build_reroute_options
from scripts.export_reroute_options import select_map_option_results
from tests.test_reroutes import segment


class RerouteOptionExportTests(unittest.TestCase):
    def test_selects_only_material_national_road_reductions_for_the_map(self):
        report = {
            "results": [
                {"segment_id": "one", "candidate_id": "strong", "decision": "manual_review", "national_reduction_m": 25_000, "distance_delta_m": 20_000},
                {"segment_id": "two", "candidate_id": "efficient", "decision": "manual_review", "national_reduction_m": 3_700, "distance_delta_m": 2_100},
                {"segment_id": "three", "candidate_id": "weak", "decision": "manual_review", "national_reduction_m": 4_000, "distance_delta_m": 9_000},
                {"segment_id": "four", "candidate_id": "rejected", "decision": "rejected", "national_reduction_m": 30_000, "distance_delta_m": 1_000},
                {"segment_id": "one", "candidate_id": "dominated", "decision": "manual_review", "national_reduction_m": 25_000, "distance_delta_m": 30_000},
                {"segment_id": "five", "candidate_id": "recommended", "decision": "candidate", "national_reduction_m": 24_000, "distance_delta_m": 18_000},
            ]
        }

        selected = select_map_option_results(report, min_national_reduction_m=10_000)

        self.assertEqual(
            [item["candidate_id"] for item in selected],
            ["strong", "efficient", "recommended"],
        )

    def test_exports_alternative_geometry_and_original_comparison(self):
        current = segment(
            segment_id="target",
            distance_m=80_000,
            national_m=30_000,
        )
        proposed = segment(
            segment_id="target",
            distance_m=100_000,
            national_m=5_000,
            unknown_m=20_000,
            subleg_distances_m=(50_000, 50_000),
        )

        payload = build_reroute_options(
            (
                RerouteOption(
                    candidate_id="county-detour",
                    label="避国道绕行线",
                    current=current,
                    proposed=proposed,
                    decision="candidate",
                ),
            )
        )

        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(
            payload["selection_summary"],
            {
                "option_count": 1,
                "recommended_count": 1,
                "distance_delta_m": 20_000,
                "national_reduction_m": 25_000,
            },
        )
        self.assertEqual(len(payload["options"]), 1)
        option = payload["options"][0]
        self.assertEqual(option["segment_id"], "target")
        self.assertEqual(option["current_distance_m"], 80_000)
        self.assertEqual(option["alternative_distance_m"], 100_000)
        self.assertEqual(option["distance_delta_m"], 20_000)
        self.assertEqual(option["national_reduction_m"], 25_000)
        self.assertEqual(option["duration_delta_s"], 0)
        self.assertEqual(option["review_status"], "recommended")
        self.assertTrue(payload["features"])
        feature = payload["features"][0]
        self.assertEqual(feature["properties"]["candidate_id"], "county-detour")
        self.assertEqual(feature["properties"]["route_role"], "alternative")
        self.assertEqual(feature["geometry"]["type"], "LineString")


if __name__ == "__main__":
    unittest.main()
