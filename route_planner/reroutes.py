"""Risk-weighted definitions and comparisons for explicit reroute probes."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from route_planner.models import PlannedSegment
from route_planner.roads import candidate_metrics


_PRIORITIES = frozenset({"P0", "P1", "P2", "SCENIC"})


@dataclass(frozen=True)
class ProbeCandidate:
    candidate_id: str
    anchor_queries: tuple[str, ...]
    road_hint: str


@dataclass(frozen=True)
class ProbeDefinition:
    segment_id: str
    priority: str
    evidence_urls: tuple[str, ...]
    candidates: tuple[ProbeCandidate, ...]
    scenic: bool = False


@dataclass(frozen=True)
class CandidateComparison:
    decision: str
    reasons: tuple[str, ...]
    national_reduction_m: int
    distance_delta_m: int
    projected_route_detour_ratio: float


def load_probe_definitions(
    path: Path, valid_segment_ids: Collection[str]
) -> tuple[ProbeDefinition, ...]:
    """Load strict probe data bound to known route segment identifiers."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Unable to load reroute probe definitions") from error
    if not isinstance(payload, dict) or not _nonempty_string(payload.get("route_id")):
        raise ValueError("probe definitions require a route_id")
    raw_probes = payload.get("probes")
    if not isinstance(raw_probes, list):
        raise ValueError("probe definitions require a probes list")

    definitions = tuple(
        _parse_probe(item, set(valid_segment_ids)) for item in raw_probes
    )
    segment_ids = [item.segment_id for item in definitions]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError("duplicate probe segment")
    return definitions


def compare_candidate(
    current: PlannedSegment,
    proposed: PlannedSegment,
    full_baseline_m: int,
    other_selected_m: int,
    max_detour_ratio: float,
) -> CandidateComparison:
    """Compare one proposed segment without losing route-wide constraints."""
    if full_baseline_m <= 0:
        raise ValueError("full_baseline_m must be positive")
    old = candidate_metrics(current.selected)
    new = candidate_metrics(proposed.selected)
    projected = (other_selected_m + proposed.selected.distance_m) / full_baseline_m
    national_reduction_m = old.national_m - new.national_m
    distance_delta_m = proposed.selected.distance_m - current.selected.distance_m

    risk_reasons = tuple(
        risk
        for risk, distance in (
            ("hard", new.hard_risk_m),
            ("freight", new.freight_risk_m),
        )
        if distance
    )
    if risk_reasons:
        decision, reasons = "rejected", risk_reasons
    elif any(distance_m > 80_000 for distance_m in proposed.subleg_distances_m):
        decision, reasons = "rejected", ("subleg_over_80_km",)
    elif projected > max_detour_ratio:
        decision, reasons = "rejected", ("route_detour_over_15_percent",)
    elif national_reduction_m <= 0:
        decision, reasons = "rejected", ("national_not_reduced",)
    elif new.unknown_m - old.unknown_m > 5_000:
        decision, reasons = "manual_review", ("unknown_increase",)
    else:
        decision, reasons = "candidate", ()
    return CandidateComparison(
        decision=decision,
        reasons=reasons,
        national_reduction_m=national_reduction_m,
        distance_delta_m=distance_delta_m,
        projected_route_detour_ratio=projected,
    )


def _parse_probe(value: Any, valid_segment_ids: set[str]) -> ProbeDefinition:
    if not isinstance(value, dict):
        raise ValueError("probe must be an object")
    segment_id = _required_string(value, "segment_id", "probe")
    if segment_id not in valid_segment_ids:
        raise ValueError(f"unknown segment: {segment_id}")
    priority = _required_string(value, "priority", f"probe {segment_id}")
    if priority not in _PRIORITIES:
        raise ValueError(f"invalid priority: {priority}")

    evidence_urls = _string_tuple(value.get("evidence_urls"), "evidence_urls")
    if priority == "P0" and not evidence_urls:
        raise ValueError("P0 evidence must not be empty")
    raw_candidates = value.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError(f"probe {segment_id} requires candidates")
    candidates = tuple(_parse_candidate(item, segment_id) for item in raw_candidates)
    candidate_ids = [item.candidate_id for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(f"duplicate candidate id in {segment_id}")
    scenic = value.get("scenic", False)
    if not isinstance(scenic, bool):
        raise ValueError(f"probe {segment_id} scenic must be boolean")
    return ProbeDefinition(
        segment_id=segment_id,
        priority=priority,
        evidence_urls=evidence_urls,
        candidates=candidates,
        scenic=scenic,
    )


def _parse_candidate(value: Any, segment_id: str) -> ProbeCandidate:
    if not isinstance(value, dict):
        raise ValueError(f"candidate in {segment_id} must be an object")
    anchors = _string_tuple(value.get("anchor_queries"), "anchor_queries")
    if not anchors:
        raise ValueError(f"candidate in {segment_id} requires an anchor")
    return ProbeCandidate(
        candidate_id=_required_string(value, "candidate_id", "candidate"),
        anchor_queries=anchors,
        road_hint=_required_string(value, "road_hint", "candidate"),
    )


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(_nonempty_string(item) for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _required_string(value: dict[str, Any], field: str, context: str) -> str:
    result = value.get(field)
    if not _nonempty_string(result):
        raise ValueError(f"{context} requires {field}")
    return result


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
