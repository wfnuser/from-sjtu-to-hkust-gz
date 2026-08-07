import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from route_planner.export import build_geojson, build_review_markdown, build_summary
from route_planner.models import (
    CandidateRoute,
    Coordinate,
    PlannedSegment,
    ReviewItem,
    RoadClass,
    RouteStep,
    SegmentRule,
    Waypoint,
)
from scripts.generate_route import write_artifacts


def _segment(
    *,
    segment_id="main-01-to-main-02",
    road_classes=(RoadClass.COUNTY, RoadClass.CYCLEWAY),
    distances=(1_200, 800),
    optional=False,
    duration_s=700,
):
    start = Waypoint(
        "start", "上海交通大学闵行校区", "上海", "上海交通大学闵行校区",
        Coordinate(121.0, 31.0), include_in_main_totals=not optional,
        branch="支线" if optional else "main",
    )
    end = Waypoint(
        "end", "海盐", "嘉兴", "海盐", Coordinate(121.2, 30.9),
        include_in_main_totals=not optional, branch="支线" if optional else "main",
    )
    steps = tuple(
        RouteStep(
            f"沿{road_class.value}骑行", f"{road_class.value}-road-{index}", distance,
            (Coordinate(121.0 + index / 100, 31.0), Coordinate(121.01 + index / 100, 31.01)),
            road_class,
        )
        for index, (road_class, distance) in enumerate(zip(road_classes, distances))
    )
    selected = CandidateRoute(0, sum(distances), duration_s, steps)
    return PlannedSegment(
        segment_id, start, end, SegmentRule(segment_id, day=2), 1_500, selected,
        sum(distances) / 1_500, (sum(distances),),
    )


class ExportTests(unittest.TestCase):
    def test_geojson_has_one_linestring_per_real_step_with_segment_context(self):
        """Would fail if export collapsed steps or replaced step metadata with segment totals."""
        data = build_geojson([_segment()])

        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 2)
        feature = data["features"][0]
        self.assertEqual(feature["geometry"]["type"], "LineString")
        self.assertEqual(feature["properties"]["segment_id"], "main-01-to-main-02")
        self.assertEqual(feature["properties"]["distance_m"], 1_200)
        self.assertEqual(feature["properties"]["segment_duration_s"], 700)
        self.assertEqual(feature["properties"]["day"], 2)
        self.assertEqual(feature["properties"]["from_name"], "上海交通大学闵行校区")
        self.assertEqual(feature["properties"]["to_name"], "海盐")
        self.assertEqual(feature["properties"]["road_class"], "county")
        self.assertIn("risk_tags", feature["properties"])
        self.assertIn("review_status", feature["properties"])
        self.assertFalse(feature["properties"]["optional_branch"])
        self.assertNotEqual(feature["geometry"]["coordinates"][0], [121.0, 31.0])

    def test_summary_separates_main_and_optional_totals_and_road_classes(self):
        """Would fail if optional branches inflated the main route or class distances."""
        main = _segment()
        optional = _segment(
            segment_id="branch-01", road_classes=(RoadClass.NATIONAL,), distances=(300,),
            optional=True, duration_s=120,
        )

        summary = build_summary([main, optional], 1.15)

        self.assertEqual(summary["main"]["distance_m"], 2_000)
        self.assertEqual(summary["main"]["duration_s"], 700)
        self.assertEqual(summary["main"]["county_distance_m"], 1_200)
        self.assertEqual(summary["main"]["cycleway_distance_m"], 800)
        self.assertEqual(summary["main"]["national_distance_m"], 0)
        self.assertEqual(summary["all_branches"]["distance_m"], 2_300)
        self.assertEqual(summary["all_branches"]["national_distance_m"], 300)
        self.assertEqual(summary["optional_branch_excluded"]["distance_m"], 300)
        self.assertAlmostEqual(summary["main"]["detour_ratio"], 2_000 / 1_500)
        self.assertEqual(summary["max_detour_ratio"], 1.15)

    def test_review_markdown_lists_manual_review_items_and_segment_details(self):
        """Would fail if the human review artifact lost route safety context."""
        segment = _segment()
        markdown = build_review_markdown([segment])

        self.assertIn("main-01-to-main-02", markdown)
        self.assertIn("上海交通大学闵行校区", markdown)
        self.assertIn("county-road-0", markdown)
        self.assertIn("人工复核", markdown)

    def test_artifact_writer_leaves_no_published_files_when_json_validation_fails(self):
        """Would fail if a bad later artifact published an earlier partial route file."""
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with self.assertRaises(TypeError):
                write_artifacts(output_dir, {"bad": {1}}, {"ok": True}, "review")

            self.assertEqual(list(output_dir.iterdir()), [])

    def test_artifact_writer_publishes_validated_geojson_summary_and_review(self):
        """Would fail if the generator omitted an artifact or published invalid JSON."""
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_artifacts(output_dir, build_geojson([_segment()]), build_summary([_segment()], 1.15), "# review\n")

            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["coastal-route.geojson", "review.md", "summary.json"],
            )
            self.assertEqual(json.loads((output_dir / "coastal-route.geojson").read_text())["type"], "FeatureCollection")
            self.assertEqual(json.loads((output_dir / "summary.json").read_text())["main"]["distance_m"], 2_000)

    def test_approved_national_exception_is_not_an_unresolved_review(self):
        """Would fail if an informational approval still blocked the route summary."""
        approved = replace(
            _segment(),
            reviews=(ReviewItem("NATIONAL_ROAD_EXCEPTION_APPROVED", "main-01-to-main-02", "info", "Reviewed."),),
        )
        pending = replace(
            _segment(),
            reviews=(ReviewItem("MANUAL_CHECK", "main-01-to-main-02", "warning", "Review this."),),
        )

        self.assertEqual(build_geojson([approved])["features"][0]["properties"]["review_status"], "approved")
        self.assertEqual(build_summary([approved], 1.15)["main"]["unresolved_count"], 0)
        self.assertEqual(build_geojson([pending])["features"][0]["properties"]["review_status"], "review_required")
        self.assertEqual(build_summary([pending], 1.15)["main"]["unresolved_count"], 1)


if __name__ == "__main__":
    unittest.main()
