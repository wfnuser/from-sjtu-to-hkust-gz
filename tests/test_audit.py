from pathlib import Path
import tempfile
import unittest

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
from scripts.audit_route import audit, scan_for_secret


def _segment(
    *,
    national=False,
    parallel_road_available=False,
    allowed_national_m=0,
    risk_tags=frozenset(),
    polyline=True,
    subleg_distances=(1_000,),
    reviews=(),
):
    segment_id = "main-01-to-main-02"
    road_class = RoadClass.NATIONAL if national else RoadClass.COUNTY
    step = RouteStep(
        "沿道路骑行", "G228国道" if national else "X101县道", 1_000,
        (Coordinate(121.0, 31.0), Coordinate(121.01, 31.01)) if polyline else (),
        road_class, risk_tags,
    )
    start = Waypoint("start", "起点", "上海", "起点", Coordinate(121.0, 31.0))
    end = Waypoint("end", "终点", "上海", "终点", Coordinate(121.1, 31.1))
    return PlannedSegment(
        segment_id, start, end,
        SegmentRule(segment_id, parallel_road_available=parallel_road_available,
                    allowed_national_m=allowed_national_m),
        1_000, CandidateRoute(0, 1_000, 300, (step,)), 1.0,
        subleg_distances, reviews,
    )


class AuditTests(unittest.TestCase):
    def test_audit_rejects_national_road_when_parallel_override_exists(self):
        """Would fail if a national-road restriction was treated as advisory."""
        result = audit([_segment(national=True, parallel_road_available=True)])

        self.assertIn("PARALLEL_ROAD_RULE_VIOLATION", [item.code for item in result.items])
        self.assertFalse(result.ok)

    def test_audit_rejects_hard_risk_steps(self):
        """Would fail if hard-exclusion tags reached generated route artifacts."""
        result = audit([_segment(risk_tags=frozenset({"hard"}))])

        self.assertIn("HARD_RISK", [item.code for item in result.items])

    def test_audit_rejects_missing_real_polyline(self):
        """Would fail if unresolved or synthetic geometry passed the final audit."""
        result = audit([_segment(polyline=False)])

        self.assertIn("UNRESOLVED_POLYLINE", [item.code for item in result.items])

    def test_audit_rejects_api_subleg_over_eighty_kilometres(self):
        """Would fail if the API subleg cap were not enforced at publication time."""
        result = audit([_segment(subleg_distances=(80_001,))])

        self.assertIn("SUBLEG_OVER_80_KM", [item.code for item in result.items])

    def test_audit_requires_explicit_review_for_national_exception(self):
        """Would fail if a permitted national-road distance silently became approved."""
        result = audit([_segment(national=True, allowed_national_m=1_000)])

        self.assertIn("NATIONAL_ROAD_EXCEPTION_UNREVIEWED", [item.code for item in result.items])

    def test_parallel_rule_respects_its_bounded_national_road_allowance(self):
        """Would fail if an allowed, reviewed exception was still reported as a violation."""
        result = audit([
            _segment(
                national=True,
                parallel_road_available=True,
                allowed_national_m=1_000,
                reviews=(ReviewItem("NATIONAL_ROAD_EXCEPTION_APPROVED", "main-01-to-main-02", "info", "Reviewed."),),
            )
        ])

        self.assertNotIn("PARALLEL_ROAD_RULE_VIOLATION", [item.code for item in result.items])
        self.assertTrue(result.ok)

    def test_audit_accepts_explicitly_reviewed_national_exception(self):
        """Would fail if a recorded national-road approval could not clear its review gate."""
        result = audit([
            _segment(
                national=True,
                allowed_national_m=1_000,
                reviews=(ReviewItem("NATIONAL_ROAD_EXCEPTION_APPROVED", "main-01-to-main-02", "info", "Reviewed."),),
            )
        ])

        self.assertNotIn("NATIONAL_ROAD_EXCEPTION_UNREVIEWED", [item.code for item in result.items])
        self.assertTrue(result.ok)

    def test_secret_scan_rejects_generated_artifact(self):
        """Would fail if generated files could retain a supplied service-key value."""
        with tempfile.TemporaryDirectory() as directory:
            leaked = Path(directory) / "summary.json"
            leaked.write_text("secret-123", encoding="utf-8")

            self.assertFalse(scan_for_secret(Path(directory), "secret-123").ok)


if __name__ == "__main__":
    unittest.main()
