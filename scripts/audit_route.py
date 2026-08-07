#!/usr/bin/env python3
"""Audit the exact transactionally published route profile before publication."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.amap import load_amap_key
from route_planner.artifacts import ArtifactPaths
from route_planner.config import load_route_config
from route_planner.manifest import load_manifest
from route_planner.models import PlannedSegment, ReviewItem, RoadClass, RouteConfig, Waypoint
from route_planner.roads import classify_risks, classify_road


NATIONAL_EXCEPTION_APPROVAL = "NATIONAL_ROAD_EXCEPTION_APPROVED"


@dataclass(frozen=True)
class AuditResult:
    items: tuple[ReviewItem, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "hard" for item in self.items)


def audit(segments: Sequence[PlannedSegment]) -> AuditResult:
    """Return all publication-blocking risks found in immutable planned segments."""
    items: list[ReviewItem] = []
    if not segments:
        items.append(_item("NO_ROUTE_OUTPUT", "", "No planned route segments were supplied."))
    for segment in segments:
        items.extend(_audit_segment(segment))
    return AuditResult(tuple(items))


def scan_for_secret(root: Path, secret: str) -> AuditResult:
    """Return a hard finding when a supplied secret is present in an artifact tree."""
    return _scan_paths_for_secret(
        sorted(candidate for candidate in root.rglob("*") if candidate.is_file()), secret
    )


def _scan_paths_for_secret(paths: Sequence[Path], secret: str) -> AuditResult:
    """Return hard findings for a fixed published artifact set."""
    if not secret:
        return AuditResult((_item("SECRET_SCAN_NOT_CONFIGURED", "", "Secret scan requires a non-empty value."),))
    items: list[ReviewItem] = []
    for path in paths:
        try:
            if secret in path.read_text(encoding="utf-8", errors="ignore"):
                items.append(_item("KEY_LEAKAGE", "", f"Secret found in generated artifact {path.name}."))
        except OSError:
            items.append(_item("ARTIFACT_UNREADABLE", "", f"Could not inspect {path.name}."))
    return AuditResult(tuple(items))


def _audit_segment(segment: PlannedSegment) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    if not segment.selected.steps or any(not step.polyline_gcj for step in segment.selected.steps):
        items.append(_item("UNRESOLVED_POLYLINE", segment.segment_id, "Route has no real API polyline."))
    for distance_m in segment.subleg_distances_m:
        if distance_m > 80_000:
            items.append(_item("SUBLEG_OVER_80_KM", segment.segment_id, "API subleg exceeds 80 km.", distance_m))
    national_distance_m = 0
    for step in segment.selected.steps:
        risk_tags = step.risk_tags | classify_risks(step.road_name, step.instruction)
        if "hard" in risk_tags:
            items.append(_item("HARD_RISK", segment.segment_id, "Hard-risk road step is selected.", step.distance_m, step.road_name))
        if "freight" in risk_tags:
            items.append(_item("FREIGHT_RISK", segment.segment_id, "Freight-risk road step is selected.", step.distance_m, step.road_name))
        if classify_road(step.road_name, step.instruction) is RoadClass.NATIONAL:
            national_distance_m += step.distance_m
    if national_distance_m:
        if segment.rule.parallel_road_available and national_distance_m > segment.rule.allowed_national_m:
            items.append(_item("PARALLEL_ROAD_RULE_VIOLATION", segment.segment_id, "National road selected despite an available parallel road.", national_distance_m))
        elif national_distance_m > segment.rule.allowed_national_m:
            items.append(_item("NATIONAL_ROAD_ALLOWANCE_EXCEEDED", segment.segment_id, "National-road distance exceeds the measured unavoidable allowance.", national_distance_m))
        elif not any(item.code == NATIONAL_EXCEPTION_APPROVAL for item in segment.reviews):
            items.append(_item("NATIONAL_ROAD_EXCEPTION_UNREVIEWED", segment.segment_id, "National-road use lacks an explicit recorded review approval.", national_distance_m))
    return items


def _item(code: str, segment_id: str, message: str, distance_m: int = 0, road_name: str = "") -> ReviewItem:
    return ReviewItem(code, segment_id, "hard", message, road_name, distance_m)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--strict", action="store_true", help="fail on any publication risk")
    parser.add_argument("--profile", choices=("coastal", "inland"), required=True)
    args = parser.parse_args(argv)
    try:
        config = load_route_config(args.config)
        paths = ArtifactPaths.for_profile(args.data_dir, args.profile)
        segments = load_manifest(paths.manifest, config.route_id)
        _require_config_alignment(config, segments)
        items = [
            *audit(segments).items,
            *_scan_paths_for_secret(
                (paths.geojson, paths.summary, paths.review, paths.manifest),
                load_amap_key(args.env),
            ).items,
        ]
    except Exception:
        print("HARD MANIFEST_INVALID: cannot audit this published route", file=sys.stdout)
        return 1
    for item in items:
        segment = f" [{item.segment_id}]" if item.segment_id else ""
        road = f" ({item.road_name}, {item.distance_m} m)" if item.road_name else ""
        print(f"{item.severity.upper()} {item.code}{segment}: {item.message}{road}")
    return 0 if not any(item.severity == "hard" for item in items) else 1


def _require_config_alignment(config: RouteConfig, segments: Sequence[PlannedSegment]) -> None:
    expected = {
        f"{start.id}-to-{end.id}": (start, end)
        for start, end in zip(config.waypoints, config.waypoints[1:])
    }
    seen: set[str] = set()
    for segment in segments:
        if segment.segment_id in seen or segment.segment_id not in expected:
            raise ValueError
        start, end = expected[segment.segment_id]
        if (
            segment.rule != config.segment_rules.get(segment.segment_id)
            or not _waypoint_matches_config(segment.from_waypoint, start)
            or not _waypoint_matches_config(segment.to_waypoint, end)
        ):
            raise ValueError
        seen.add(segment.segment_id)


def _waypoint_matches_config(actual: Waypoint, configured: Waypoint) -> bool:
    return (
        actual.id,
        actual.name,
        actual.city,
        actual.query,
        actual.required,
        actual.include_in_main_totals,
        actual.branch,
    ) == (
        configured.id,
        configured.name,
        configured.city,
        configured.query,
        configured.required,
        configured.include_in_main_totals,
        configured.branch,
    )


if __name__ == "__main__":
    raise SystemExit(main())
