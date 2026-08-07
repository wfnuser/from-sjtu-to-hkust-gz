import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from route_planner.amap import AmapClient
from route_planner.export import build_geojson, build_review_markdown, build_summary
from route_planner.manifest import build_manifest
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
from scripts.generate_route import write_artifacts


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

    def test_audit_rejects_national_distance_over_measured_allowance_even_without_parallel(self):
        result = audit(
            [
                _segment(
                    national=True,
                    allowed_national_m=999,
                    reviews=(
                        ReviewItem(
                            "NATIONAL_ROAD_EXCEPTION_APPROVED",
                            "main-01-to-main-02",
                            "info",
                            "Reviewed.",
                        ),
                    ),
                )
            ]
        )

        self.assertFalse(result.ok)
        self.assertIn("NATIONAL_ROAD_ALLOWANCE_EXCEEDED", [item.code for item in result.items])

    def test_secret_scan_rejects_generated_artifact(self):
        """Would fail if generated files could retain a supplied service-key value."""
        with tempfile.TemporaryDirectory() as directory:
            leaked = Path(directory) / "summary.json"
            leaked.write_text("secret-123", encoding="utf-8")

            self.assertFalse(scan_for_secret(Path(directory), "secret-123").ok)

    def test_generate_cli_task7_contract_publishes_the_manifest_strict_audit_reads(self):
        """Would fail if either CLI ignored its Task 7 inputs or audited a fixture instead."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, resolutions, environment, cache_dir = _write_live_inputs(root)
            output_dir = root / "web-data"

            generated = _run_cli(
                "scripts/generate_route.py",
                "--config", config,
                "--resolutions", resolutions,
                "--env", environment,
                "--output-dir", output_dir,
                "--cache-dir", cache_dir,
            )
            audited = _run_cli(
                "scripts/audit_route.py",
                "--config", config,
                "--data-dir", output_dir,
                "--env", environment,
                "--strict",
            )

            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual(audited.returncode, 0, audited.stderr)
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["coastal-route.geojson", "review.md", "route-manifest.json", "summary.json"],
            )
            self.assertNotIn("sanitized-test-key", generated.stdout + generated.stderr + audited.stdout + audited.stderr)

    def test_strict_audit_rejects_unsafe_manifest_that_was_published_with_route_artifacts(self):
        """Would fail if strict audit certified its safe fixture instead of the manifest route."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, _, environment, _ = _write_live_inputs(root)
            output_dir = root / "web-data"
            unsafe = _config_aligned_segment(risk_tags=frozenset({"hard"}))
            write_artifacts(
                output_dir,
                build_geojson([unsafe]),
                build_summary([unsafe], 1.15),
                build_review_markdown([unsafe]),
                build_manifest("cli-test", [unsafe]),
            )

            audited = _run_cli(
                "scripts/audit_route.py",
                "--config", config,
                "--data-dir", output_dir,
                "--env", environment,
                "--strict",
            )

            self.assertNotEqual(audited.returncode, 0)
            self.assertIn("HARD_RISK", audited.stdout)
            self.assertNotIn("sanitized-test-key", audited.stdout + audited.stderr)

    def test_strict_audit_rejects_manifest_with_a_rule_that_disagrees_with_config(self):
        """Would fail if a manifest could weaken the configured national-road policy."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, _, environment, _ = _write_live_inputs(root)
            output_dir = root / "web-data"
            configured_start = Waypoint("main-01", "上海交通大学闵行校区", "上海", "上海交通大学闵行校区", Coordinate(121.0, 31.0))
            configured_end = Waypoint("main-02", "香港科技大学（广州）", "广州", "香港科技大学（广州）", Coordinate(113.0, 23.0))
            mismatched = replace(
                _segment(),
                from_waypoint=configured_start,
                to_waypoint=configured_end,
                rule=SegmentRule("main-01-to-main-02", allowed_national_m=1),
            )
            write_artifacts(
                output_dir,
                build_geojson([mismatched]),
                build_summary([mismatched], 1.15),
                build_review_markdown([mismatched]),
                build_manifest("cli-test", [mismatched]),
            )

            audited = _run_cli(
                "scripts/audit_route.py",
                "--config", config,
                "--data-dir", output_dir,
                "--env", environment,
                "--strict",
            )

            self.assertNotEqual(audited.returncode, 0)
            self.assertIn("MANIFEST_INVALID", audited.stdout)


def _write_live_inputs(root):
    config = root / "route.json"
    config.write_text(
        json.dumps(
            {
                "route_id": "cli-test",
                "max_detour_ratio": 1.15,
                "waypoints": [
                    {"id": "main-01", "name": "上海交通大学闵行校区", "city": "上海", "query": "上海交通大学闵行校区", "coordinate": None},
                    {"id": "main-02", "name": "香港科技大学（广州）", "city": "广州", "query": "香港科技大学（广州）", "coordinate": None},
                ],
                "checkin_waypoints": [],
                "segment_rules": {"main-01-to-main-02": {"segment_id": "main-01-to-main-02"}},
                "optional_branches": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    resolutions = root / "resolutions.json"
    resolutions.write_text(
        json.dumps(
            {
                "resolutions": [
                    {"query": "上海交通大学闵行校区", "city": "上海", "candidates": [{"location_gcj": {"lon": 121.0, "lat": 31.0}, "selected": True}]},
                    {"query": "香港科技大学（广州）", "city": "广州", "candidates": [{"location_gcj": {"lon": 113.0, "lat": 23.0}, "selected": True}]},
                ],
                "unresolved_queries": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    environment = root / ".env"
    environment.write_text("AMAP_WEB_SERVICE_KEY=sanitized-test-key\n", encoding="utf-8")
    cache_dir = root / "cache"
    client = AmapClient("sanitized-test-key", cache_dir, min_interval_s=0)
    cache_key = client.cache_key(
        "/v5/direction/electrobike",
        {"origin": "121.0,31.0", "destination": "113.0,23.0", "show_fields": "polyline", "alternative_route": "3"},
    )
    (cache_dir / f"{cache_key}.json").write_text(
        json.dumps(
            {"status": "1", "route": {"paths": [{"distance": "1000", "duration": "300", "steps": [{"instruction": "沿X101县道骑行", "road_name": "X101县道", "step_distance": "1000", "polyline": "121.0,31.0;113.0,23.0"}]}]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config, resolutions, environment, cache_dir


def _config_aligned_segment(**kwargs):
    return replace(
        _segment(**kwargs),
        from_waypoint=Waypoint("main-01", "上海交通大学闵行校区", "上海", "上海交通大学闵行校区", Coordinate(121.0, 31.0)),
        to_waypoint=Waypoint("main-02", "香港科技大学（广州）", "广州", "香港科技大学（广州）", Coordinate(113.0, 23.0)),
    )


def _run_cli(script, *arguments):
    return subprocess.run(
        [sys.executable, script, *(str(argument) for argument in arguments)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
