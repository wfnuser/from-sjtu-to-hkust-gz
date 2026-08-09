#!/usr/bin/env python3
"""Probe explicit inland reroutes without publishing them as the main route."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.amap import AmapClient, load_amap_key
from route_planner.manifest import load_manifest
from route_planner.models import PlannedSegment
from route_planner.planner import RoutePlanner
from route_planner.reroutes import (
    ProbeCandidate,
    ProbeDefinition,
    compare_candidate,
    load_probe_definitions,
)
from route_planner.roads import ReviewRequired, candidate_metrics
from scripts.generate_route import load_resolved_config


def ordered_probes(
    definitions: tuple[ProbeDefinition, ...],
    current_by_id: dict[str, PlannedSegment],
    priority: str,
) -> tuple[ProbeDefinition, ...]:
    """Return one priority bucket, longest current national exposure first."""
    selected = tuple(item for item in definitions if item.priority == priority)
    if not selected:
        raise ValueError(f"No {priority} probes are configured")
    missing = {item.segment_id for item in selected} - current_by_id.keys()
    if missing:
        raise ValueError("Probe definitions do not match the published manifest")
    return tuple(
        sorted(
            selected,
            key=lambda item: (
                -candidate_metrics(current_by_id[item.segment_id].selected).national_m,
                item.segment_id,
            ),
        )
    )


def evaluate_proposed_candidate(
    definition: ProbeDefinition,
    candidate: ProbeCandidate,
    current: PlannedSegment,
    proposed: PlannedSegment,
    published_segments: tuple[PlannedSegment, ...],
    max_detour_ratio: float,
) -> dict[str, object]:
    """Render a JSON-safe before/after comparison for one planned candidate."""
    full_baseline_m = sum(item.baseline_distance_m for item in published_segments)
    other_selected_m = sum(
        item.selected.distance_m
        for item in published_segments
        if item.segment_id != current.segment_id
    )
    comparison = compare_candidate(
        current,
        proposed,
        full_baseline_m,
        other_selected_m,
        max_detour_ratio,
    )
    return {
        "segment_id": definition.segment_id,
        "priority": definition.priority,
        "scenic": definition.scenic,
        "candidate_id": candidate.candidate_id,
        "road_hint": candidate.road_hint,
        "evidence_urls": list(definition.evidence_urls),
        "from_name": current.from_waypoint.name,
        "to_name": current.to_waypoint.name,
        "decision": comparison.decision,
        "reasons": list(comparison.reasons),
        "national_reduction_m": comparison.national_reduction_m,
        "distance_delta_m": comparison.distance_delta_m,
        "projected_route_detour_ratio": comparison.projected_route_detour_ratio,
        "current": _segment_report(current, current.rule.anchor_queries),
        "proposed": _segment_report(proposed, candidate.anchor_queries),
    }


def plan_probe(
    planner: RoutePlanner,
    definition: ProbeDefinition,
    candidate: ProbeCandidate,
    current: PlannedSegment,
    published_segments: tuple[PlannedSegment, ...],
    max_detour_ratio: float,
) -> dict[str, object]:
    """Plan one live candidate and compare it without mutating publication state."""
    proposed_rule = replace(
        current.rule,
        anchor_queries=candidate.anchor_queries,
        parallel_road_available=False,
        allowed_national_m=0,
        national_exception_reason="",
    )
    proposed = planner.plan_segment(
        current.from_waypoint,
        current.to_waypoint,
        proposed_rule,
    )
    return evaluate_proposed_candidate(
        definition,
        candidate,
        current,
        proposed,
        published_segments,
        max_detour_ratio,
    )


def run_probe_candidates(
    planner: RoutePlanner,
    definition: ProbeDefinition,
    current: PlannedSegment,
    published_segments: tuple[PlannedSegment, ...],
    max_detour_ratio: float,
    report: dict[str, object],
    report_path: Path,
) -> dict[str, object]:
    """Persist every candidate outcome and continue past review-only failures."""
    completed = {
        _result_key(item)
        for item in _list_of_mappings(report.get("results"), "report results")
        if item.get("decision") != "probe_failed"
    }
    for candidate in definition.candidates:
        key = (definition.segment_id, candidate.candidate_id)
        if key in completed:
            continue
        try:
            result = plan_probe(
                planner,
                definition,
                candidate,
                current,
                published_segments,
                max_detour_ratio,
            )
        except ReviewRequired as error:
            result = _failed_probe_report(definition, candidate, current, error)
        report = merge_result(report, result)
        write_report(report_path, report)
        completed.add(key)
        print(
            f"{definition.segment_id} {candidate.candidate_id}: "
            f"{result['decision']} national_delta={result['national_reduction_m']}m"
        )
    return report


def merge_result(
    report: dict[str, object], result: dict[str, object]
) -> dict[str, object]:
    """Insert or replace one candidate result while retaining prior probes."""
    results = _list_of_mappings(report.get("results"), "report results")
    key = _result_key(result)
    merged = [item for item in results if _result_key(item) != key]
    merged.append(dict(result))
    return {**report, "results": merged}


def write_report(path: Path, report: dict[str, object]) -> None:
    """Atomically persist a valid report after every successful candidate."""
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    json.loads(rendered)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_report(path: Path, route_id: str) -> dict[str, object]:
    """Load a resumable report or initialize an empty one for this route."""
    if not path.exists():
        return {"schema_version": 1, "route_id": route_id, "results": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Unable to resume invalid reroute report") from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("route_id") != route_id
    ):
        raise ValueError("Reroute report does not match the route")
    _list_of_mappings(value.get("results"), "report results")
    return value


def _segment_report(
    segment: PlannedSegment, anchor_queries: tuple[str, ...]
) -> dict[str, object]:
    metrics = candidate_metrics(segment.selected)
    return {
        "distance_m": segment.selected.distance_m,
        "duration_s": segment.selected.duration_s,
        "baseline_distance_m": segment.baseline_distance_m,
        "segment_detour_ratio": segment.detour_ratio,
        "national_m": metrics.national_m,
        "unknown_m": metrics.unknown_m,
        "freight_risk_m": metrics.freight_risk_m,
        "hard_risk_m": metrics.hard_risk_m,
        "subleg_distances_m": list(segment.subleg_distances_m),
        "anchor_queries": list(anchor_queries),
        "road_names": list(
            dict.fromkeys(
                step.road_name or "未命名道路" for step in segment.selected.steps
            )
        ),
    }


def _failed_probe_report(
    definition: ProbeDefinition,
    candidate: ProbeCandidate,
    current: PlannedSegment,
    error: ReviewRequired,
) -> dict[str, object]:
    return {
        "segment_id": definition.segment_id,
        "priority": definition.priority,
        "scenic": definition.scenic,
        "candidate_id": candidate.candidate_id,
        "road_hint": candidate.road_hint,
        "evidence_urls": list(definition.evidence_urls),
        "from_name": current.from_waypoint.name,
        "to_name": current.to_waypoint.name,
        "decision": "probe_failed",
        "reasons": list(error.reasons),
        "national_reduction_m": 0,
        "distance_delta_m": 0,
        "projected_route_detour_ratio": None,
        "current": _segment_report(current, current.rule.anchor_queries),
        "proposed": None,
    }


def _result_key(value: dict[str, object]) -> tuple[str, str]:
    segment_id = value.get("segment_id")
    candidate_id = value.get("candidate_id")
    if not isinstance(segment_id, str) or not segment_id:
        raise ValueError("result requires segment_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("result requires candidate_id")
    return segment_id, candidate_id


def _list_of_mappings(value: Any, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return [dict(item) for item in value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--priority", choices=("P0", "SCENIC", "P1", "P2"), required=True)
    args = parser.parse_args(argv)

    try:
        config = load_resolved_config(args.config, args.resolutions)
        published = load_manifest(args.manifest, config.route_id)
        current_by_id = {item.segment_id: item for item in published}
        if len(current_by_id) != len(published):
            raise ValueError("Published manifest contains duplicate segments")
        definitions = load_probe_definitions(args.probes, set(current_by_id))
        selected = ordered_probes(definitions, current_by_id, args.priority)
        report = load_report(args.report, config.route_id)
        planner = RoutePlanner(AmapClient(load_amap_key(args.env), args.cache_dir))
        for definition in selected:
            current = current_by_id[definition.segment_id]
            report = run_probe_candidates(
                planner,
                definition,
                current,
                published,
                config.max_detour_ratio,
                report,
                args.report,
            )
    except Exception as error:
        print(f"ERROR: reroute probing stopped: {error}", file=sys.stderr)
        return 1
    print(f"Wrote reroute probe report to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
