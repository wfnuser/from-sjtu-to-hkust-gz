#!/usr/bin/env python3
"""Publish reviewed reroute decisions aligned with measured route data."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.manifest import load_manifest
from route_planner.roads import candidate_metrics
from scripts.generate_route import load_resolved_config


_PRIORITIES = {"P0", "P1"}
_STATUSES = {"adopted", "rejected", "manual_review"}


def build_decision_artifact(
    route_id: str,
    probes_payload: dict[str, object],
    report_payload: dict[str, object],
    reviews_payload: dict[str, object],
    published_segments,
) -> dict[str, object]:
    """Join human-reviewed choices to their exact measured candidate results."""
    for label, payload in (
        ("probes", probes_payload),
        ("report", report_payload),
        ("reviews", reviews_payload),
    ):
        if payload.get("route_id") != route_id:
            raise ValueError(f"{label} route_id does not match the published route")

    probes = _objects(probes_payload.get("probes"), "probes")
    results = _objects(report_payload.get("results"), "report results")
    reviews = _objects(reviews_payload.get("reviews"), "reviews")
    required = {
        _required_text(probe, "segment_id")
        for probe in probes
        if probe.get("priority") in _PRIORITIES
    }
    review_by_segment = _unique_by(reviews, "segment_id", "reviews")
    if set(review_by_segment) != required:
        raise ValueError("reviews must cover every P0/P1 segment exactly once")

    probe_by_segment = {
        _required_text(probe, "segment_id"): probe
        for probe in probes
        if probe.get("priority") in _PRIORITIES
    }
    result_by_key = {
        (_required_text(result, "segment_id"), _required_text(result, "candidate_id")): result
        for result in results
    }
    decisions: list[dict[str, object]] = []
    for segment_id in sorted(required, key=lambda value: _priority_key(probe_by_segment[value])):
        review = review_by_segment[segment_id]
        probe = probe_by_segment[segment_id]
        candidate_id = _required_text(review, "selected_candidate_id")
        candidate_ids = {
            _required_text(candidate, "candidate_id")
            for candidate in _objects(probe.get("candidates"), "probe candidates")
        }
        if candidate_id not in candidate_ids:
            raise ValueError(f"review candidate is not configured for {segment_id}")
        result = result_by_key.get((segment_id, candidate_id))
        if result is None:
            raise ValueError(f"review candidate has no measured result for {segment_id}")
        status = _required_text(review, "status")
        if status not in _STATUSES:
            raise ValueError(f"unsupported review status for {segment_id}")
        decisions.append(
            {
                "segment_id": segment_id,
                "priority": probe["priority"],
                "from_name": result["from_name"],
                "to_name": result["to_name"],
                "status": status,
                "selected_candidate_id": candidate_id,
                "candidate_result": result["decision"],
                "evidence_urls": list(probe.get("evidence_urls", [])),
                "evidence_conclusion": _required_text(review, "evidence_conclusion"),
                "decision_reason": _required_text(review, "decision_reason"),
                "national_reduction_m": result["national_reduction_m"],
                "distance_delta_m": result["distance_delta_m"],
                "projected_route_detour_ratio": result["projected_route_detour_ratio"],
                "current": result["current"],
                "proposed": result["proposed"],
            }
        )

    remaining = []
    for segment in sorted(
        published_segments,
        key=lambda item: -candidate_metrics(item.selected).national_m,
    ):
        national_m = candidate_metrics(segment.selected).national_m
        if not national_m:
            continue
        remaining.append(
            {
                "segment_id": segment.segment_id,
                "from_name": segment.from_waypoint.name,
                "to_name": segment.to_waypoint.name,
                "national_m": national_m,
            }
        )
    counts = Counter(item["status"] for item in decisions)
    return {
        "schema_version": 1,
        "route_id": route_id,
        "summary": {
            "decision_count": len(decisions),
            "adopted_count": counts["adopted"],
            "manual_review_count": counts["manual_review"],
            "rejected_count": counts["rejected"],
            "remaining_national_m": sum(item["national_m"] for item in remaining),
        },
        "decisions": decisions,
        "remaining_national_segments": remaining,
    }


def _priority_key(probe: dict[str, object]) -> tuple[int, str]:
    priority = _required_text(probe, "priority")
    return ({"P0": 0, "P1": 1}.get(priority, 2), _required_text(probe, "segment_id"))


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return [dict(item) for item in value]


def _unique_by(
    values: list[dict[str, object]], key: str, label: str
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for value in values:
        item_key = _required_text(value, key)
        if item_key in result:
            raise ValueError(f"duplicate {key} in {label}: {item_key}")
        result[item_key] = value
    return result


def _required_text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    json.loads(rendered)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = load_resolved_config(args.config, args.resolutions)
        segments = load_manifest(args.manifest, config.route_id)
        payload = build_decision_artifact(
            config.route_id,
            _read_json(args.probes),
            _read_json(args.report),
            _read_json(args.reviews),
            segments,
        )
        _write_json(args.output, payload)
    except Exception as error:
        print(f"ERROR: reroute decision export stopped: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {len(payload['decisions'])} reroute decisions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
