"""Lossless, JSON-safe representation of immutable planned route segments."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

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


def build_manifest(route_id: str, segments: Sequence[PlannedSegment]) -> dict[str, object]:
    """Return the complete planned values that produced a published artifact set."""
    return {
        "schema_version": 1,
        "route_id": route_id,
        "segments": [_segment_data(segment) for segment in segments],
    }


def load_manifest(path: Path, expected_route_id: str) -> tuple[PlannedSegment, ...]:
    """Load one complete manifest only when it belongs to the supplied route config."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        manifest = _mapping(value)
        if manifest.get("schema_version") != 1 or manifest.get("route_id") != expected_route_id:
            raise ValueError
        return tuple(_segment_from_data(_mapping(item)) for item in _list(manifest.get("segments")))
    except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError, KeyError) as error:
        raise ValueError("Invalid route manifest.") from error


def _segment_data(segment: PlannedSegment) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "from_waypoint": _waypoint_data(segment.from_waypoint),
        "to_waypoint": _waypoint_data(segment.to_waypoint),
        "rule": {
            "segment_id": segment.rule.segment_id,
            "anchor_queries": list(segment.rule.anchor_queries),
            "parallel_road_available": segment.rule.parallel_road_available,
            "allowed_national_m": segment.rule.allowed_national_m,
            "day": segment.rule.day,
            "national_exception_reason": segment.rule.national_exception_reason,
        },
        "baseline_distance_m": segment.baseline_distance_m,
        "selected": {
            "source_index": segment.selected.source_index,
            "distance_m": segment.selected.distance_m,
            "duration_s": segment.selected.duration_s,
            "steps": [
                {
                    "instruction": step.instruction,
                    "road_name": step.road_name,
                    "distance_m": step.distance_m,
                    "polyline_gcj": [_coordinate_data(point) for point in step.polyline_gcj],
                    "road_class": step.road_class.value,
                    "risk_tags": sorted(step.risk_tags),
                }
                for step in segment.selected.steps
            ],
        },
        "detour_ratio": segment.detour_ratio,
        "subleg_distances_m": list(segment.subleg_distances_m),
        "reviews": [
            {
                "code": review.code,
                "segment_id": review.segment_id,
                "severity": review.severity,
                "message": review.message,
                "road_name": review.road_name,
                "distance_m": review.distance_m,
            }
            for review in segment.reviews
        ],
    }


def _waypoint_data(waypoint: Waypoint) -> dict[str, object]:
    return {
        "id": waypoint.id,
        "name": waypoint.name,
        "city": waypoint.city,
        "query": waypoint.query,
        "coordinate": _coordinate_data(waypoint.coordinate) if waypoint.coordinate else None,
        "required": waypoint.required,
        "include_in_main_totals": waypoint.include_in_main_totals,
        "branch": waypoint.branch,
    }


def _coordinate_data(coordinate: Coordinate) -> dict[str, float]:
    return {"lon": coordinate.lon, "lat": coordinate.lat}


def _segment_from_data(value: dict[str, Any]) -> PlannedSegment:
    selected = _mapping(value["selected"])
    steps = tuple(_step_from_data(_mapping(item)) for item in _list(selected["steps"]))
    return PlannedSegment(
        _string(value["segment_id"]),
        _waypoint_from_data(_mapping(value["from_waypoint"])),
        _waypoint_from_data(_mapping(value["to_waypoint"])),
        _rule_from_data(_mapping(value["rule"])),
        _integer(value["baseline_distance_m"]),
        CandidateRoute(
            _integer(selected["source_index"]),
            _integer(selected["distance_m"]),
            _integer(selected["duration_s"]),
            steps,
        ),
        _number(value["detour_ratio"]),
        tuple(_integer(item) for item in _list(value["subleg_distances_m"])),
        tuple(_review_from_data(_mapping(item)) for item in _list(value.get("reviews", []))),
    )


def _waypoint_from_data(value: dict[str, Any]) -> Waypoint:
    coordinate = value.get("coordinate")
    return Waypoint(
        _string(value["id"]), _string(value["name"]), _string(value["city"]), _string(value["query"]),
        _coordinate_from_data(_mapping(coordinate)) if coordinate is not None else None,
        _bool(value["required"]), _bool(value["include_in_main_totals"]), _string(value["branch"]),
    )


def _rule_from_data(value: dict[str, Any]) -> SegmentRule:
    day = value.get("day")
    return SegmentRule(
        _string(value["segment_id"]), tuple(_string(item) for item in _list(value["anchor_queries"])),
        _bool(value["parallel_road_available"]), _integer(value["allowed_national_m"]),
        _integer(day) if day is not None else None,
        _string(value.get("national_exception_reason", "")),
    )


def _step_from_data(value: dict[str, Any]) -> RouteStep:
    return RouteStep(
        _string(value["instruction"]), _string(value["road_name"]), _integer(value["distance_m"]),
        tuple(_coordinate_from_data(_mapping(item)) for item in _list(value["polyline_gcj"])),
        RoadClass(_string(value["road_class"])), frozenset(_string(item) for item in _list(value["risk_tags"])),
    )


def _review_from_data(value: dict[str, Any]) -> ReviewItem:
    return ReviewItem(
        _string(value["code"]), _string(value["segment_id"]), _string(value["severity"]),
        _string(value["message"]), _string(value.get("road_name", "")), _integer(value.get("distance_m", 0)),
    )


def _coordinate_from_data(value: dict[str, Any]) -> Coordinate:
    return Coordinate(_number(value["lon"]), _number(value["lat"]))


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError
    return value


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError
    return value


def _integer(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError
    return value


def _number(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError
    return float(value)


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError
    return value
