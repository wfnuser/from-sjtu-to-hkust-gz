#!/usr/bin/env python3
"""Audit planned routes and generated artifacts before publication."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from collections.abc import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.models import PlannedSegment, ReviewItem
from route_planner.roads import classify_risks
from scripts.generate_route import deterministic_segments


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
    if not secret:
        return AuditResult((_item("SECRET_SCAN_NOT_CONFIGURED", "", "Secret scan requires a non-empty value."),))
    items: list[ReviewItem] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        try:
            if secret in path.read_text(encoding="utf-8", errors="ignore"):
                items.append(_item("KEY_LEAKAGE", "", f"Secret found in generated artifact {path.name}."))
        except OSError:
            items.append(_item("ARTIFACT_UNREADABLE", "", f"Could not inspect {path.name}."))
    return AuditResult(tuple(items))


def _audit_segment(segment: PlannedSegment) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    if not segment.selected.steps or any(
        not step.polyline_gcj for step in segment.selected.steps
    ):
        items.append(_item("UNRESOLVED_POLYLINE", segment.segment_id, "Route has no real API polyline."))
    for distance_m in segment.subleg_distances_m:
        if distance_m > 80_000:
            items.append(
                _item("SUBLEG_OVER_80_KM", segment.segment_id, "API subleg exceeds 80 km.", distance_m)
            )
    national_distance_m = 0
    for step in segment.selected.steps:
        risk_tags = step.risk_tags | classify_risks(step.road_name, step.instruction)
        if "hard" in risk_tags:
            items.append(_item("HARD_RISK", segment.segment_id, "Hard-risk road step is selected.", step.distance_m, step.road_name))
        if step.road_class.value == "national":
            national_distance_m += step.distance_m
    if national_distance_m:
        if (
            segment.rule.parallel_road_available
            and national_distance_m > segment.rule.allowed_national_m
        ):
            items.append(
                _item(
                    "PARALLEL_ROAD_RULE_VIOLATION", segment.segment_id,
                    "National road selected despite an available parallel road.", national_distance_m,
                )
            )
        elif not any(item.code == NATIONAL_EXCEPTION_APPROVAL for item in segment.reviews):
            items.append(
                _item(
                    "NATIONAL_ROAD_EXCEPTION_UNREVIEWED", segment.segment_id,
                    "National-road use lacks an explicit recorded review approval.", national_distance_m,
                )
            )
    return items


def _item(
    code: str, segment_id: str, message: str, distance_m: int = 0, road_name: str = ""
) -> ReviewItem:
    return ReviewItem(code, segment_id, "hard", message, road_name, distance_m)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="require an explicit secret scan")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "web" / "data")
    parser.add_argument("--secret", help="secret value to scan for; never echoed")
    args = parser.parse_args(argv)

    result = audit(deterministic_segments())
    secret_result = (
        scan_for_secret(args.data_dir, args.secret)
        if args.secret is not None
        else AuditResult(())
    )
    items = [*result.items, *secret_result.items]
    if args.strict and args.secret is None:
        items.append(_item("SECRET_SCAN_NOT_CONFIGURED", "", "Strict audit requires --secret."))
    for item in items:
        print(f"{item.severity.upper()} {item.code}: {item.message}")
    return 0 if not any(item.severity == "hard" for item in items) else 1


if __name__ == "__main__":
    raise SystemExit(main())
