import json
from pathlib import Path
import tempfile
import unittest

from route_planner.config import load_route_config
from route_planner.export import build_review_markdown, build_summary
from route_planner.models import (
    CandidateRoute,
    Coordinate,
    PlannedSegment,
    RoadClass,
    RouteStep,
    RouteConfig,
    SegmentRule,
    Waypoint,
)
from scripts.generate_route import generate_from_segments


def _schedule_segment(index: int) -> PlannedSegment:
    segment_id = f"main-{index:02d}-to-main-{index + 1:02d}"
    start = Waypoint(
        f"main-{index:02d}", f"站点{index}", "测试市", f"站点{index}",
        Coordinate(120 + index / 100, 30),
    )
    end = Waypoint(
        f"main-{index + 1:02d}", f"站点{index + 1}", "测试市", f"站点{index + 1}",
        Coordinate(120 + (index + 1) / 100, 30),
    )
    selected = CandidateRoute(
        0,
        100_000,
        18_000,
        (
            RouteStep(
                "沿X101县道骑行",
                "X101县道",
                100_000,
                (start.coordinate, end.coordinate),
                RoadClass.COUNTY,
            ),
        ),
    )
    return PlannedSegment(
        segment_id,
        start,
        end,
        SegmentRule(segment_id),
        100_000,
        selected,
        1.0,
        (100_000,),
        subleg_durations_s=(18_000,),
    )


class InlandRouteAcceptanceTests(unittest.TestCase):
    def test_every_adjacent_inland_waypoint_has_an_explicit_safety_rule(self):
        """Would fail if full generation reaches a leg with no declared policy."""
        config = load_route_config(Path("config/inland-route.json"))
        expected = {
            f"{start.id}-to-{end.id}"
            for start, end in zip(config.waypoints, config.waypoints[1:])
        }

        self.assertEqual(set(config.segment_rules), expected)
        self.assertTrue(
            all(rule.segment_id == segment_id for segment_id, rule in config.segment_rules.items())
        )

    def test_inland_schedule_accepts_fifteen_riding_days_with_three_day_buffer(self):
        """Would fail if the 18 natural days replaced the 15-day riding cap."""
        summary = build_summary(
            tuple(_schedule_segment(index) for index in range(1, 16)),
            1.15,
            profile="inland",
        )

        self.assertEqual(summary["schedule"]["deadline_start"], "2026-08-13")
        self.assertEqual(summary["schedule"]["deadline_end"], "2026-08-30")
        self.assertEqual(summary["schedule"]["deadline_available_days"], 18)
        self.assertEqual(summary["schedule"]["max_riding_days"], 15)
        self.assertEqual(summary["schedule"]["buffer_days"], 3)
        self.assertEqual(summary["schedule"]["required_work_hours_per_day"], 4)
        self.assertEqual(summary["schedule"]["max_riding_hours_per_day"], 6)
        self.assertTrue(summary["schedule"]["daily_time_constraints_met"])
        self.assertTrue(summary["schedule"]["deadline_feasible"])
        self.assertIn("内陆路线可在", summary["schedule"]["deadline_note"])
        self.assertNotIn("沿海安全优先路线", summary["schedule"]["deadline_note"])
        self.assertIn(
            summary["schedule"]["deadline_note"],
            build_review_markdown(
                tuple(_schedule_segment(index) for index in range(1, 16)),
                profile="inland",
            ),
        )

    def test_inland_schedule_rejects_sixteen_riding_days_despite_eighteen_natural_days(self):
        """Would fail if the three buffer days could be used for riding."""
        summary = build_summary(
            tuple(_schedule_segment(index) for index in range(1, 17)),
            1.15,
            profile="inland",
        )

        self.assertEqual(summary["schedule"]["day_count"], 16)
        self.assertEqual(summary["schedule"]["deadline_available_days"], 18)
        self.assertEqual(summary["schedule"]["max_riding_days"], 15)
        self.assertEqual(summary["schedule"]["buffer_days"], 3)
        self.assertFalse(summary["schedule"]["deadline_feasible"])
        self.assertIn("需16个骑行日", summary["schedule"]["deadline_note"])
        self.assertIn("最多15个骑行日", summary["schedule"]["deadline_note"])
        review = build_review_markdown(
            tuple(_schedule_segment(index) for index in range(1, 17)),
            profile="inland",
        )
        self.assertIn("## 非执行排程诊断", review)
        self.assertIn("需16个骑行日", review)
        self.assertIn("最多15个骑行日", review)
        self.assertIn("超出1天", review)
        self.assertNotIn("## 每日计划", review)

    def test_default_profile_retains_the_coastal_infeasible_note(self):
        """Protects the existing coastal output contract while inland diverges."""
        summary = build_summary(
            tuple(_schedule_segment(index) for index in range(1, 17)),
            1.15,
        )

        self.assertIn("沿海安全优先路线", summary["schedule"]["deadline_note"])
        self.assertIn("需16个骑行日", summary["schedule"]["deadline_note"])
        self.assertIn("最多15个骑行日", summary["schedule"]["deadline_note"])

    def test_inland_generation_forwards_profile_to_both_schedule_artifacts(self):
        """Would fail if generation silently rendered either artifact as coastal."""
        segments = tuple(_schedule_segment(index) for index in range(1, 16))
        config = RouteConfig("schedule-test", 1.15, (), (), {}, {})
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)

            generate_from_segments(config, segments, output_dir, profile="inland")

            summary = json.loads(
                (output_dir / "inland-summary.json").read_text(encoding="utf-8")
            )
            review = (output_dir / "inland-review.md").read_text(encoding="utf-8")
        self.assertIn("内陆路线可在", summary["schedule"]["deadline_note"])
        self.assertIn(summary["schedule"]["deadline_note"], review)


if __name__ == "__main__":
    unittest.main()
