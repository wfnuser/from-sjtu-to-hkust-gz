"""Stable GeoJSON and human-review exports for planned route segments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from route_planner.coordinates import gcj02_to_wgs84
from route_planner.models import Coordinate, PlannedSegment, RoadClass, RouteStep


def build_geojson(segments: Sequence[PlannedSegment]) -> dict[str, object]:
    """Return one WGS84 LineString feature for every API road step with geometry."""
    features: list[dict[str, object]] = []
    for segment in segments:
        for step in segment.selected.steps:
            if not step.polyline_gcj:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            _position(point) for point in step.polyline_gcj
                        ],
                    },
                    "properties": _step_properties(segment, step),
                }
            )
    return {"type": "FeatureCollection", "features": features}


def build_summary(
    segments: Sequence[PlannedSegment], max_detour_ratio: float
) -> dict[str, object]:
    """Summarize main-route totals separately from optional branches."""
    main = tuple(segment for segment in segments if not _is_optional(segment))
    optional = tuple(segment for segment in segments if _is_optional(segment))
    return {
        "max_detour_ratio": max_detour_ratio,
        "main": _totals(main),
        "all_branches": _totals(segments),
        "optional_branch_excluded": _totals(optional),
    }


def build_review_markdown(segments: Sequence[PlannedSegment]) -> str:
    """Render the route and its unresolved review work for a human reviewer."""
    lines = [
        "# 路线人工复核",
        "",
        "每条道路均来自 API 步骤；国道例外须以 `NATIONAL_ROAD_EXCEPTION_APPROVED` 复核项明确记录。",
        "",
        "| 路段 | 起点 | 终点 | 距离 (m) | 时长 (s) | 复核状态 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for segment in segments:
        lines.append(
            "| {segment_id} | {from_name} | {to_name} | {distance} | {duration} | {status} |".format(
                segment_id=segment.segment_id,
                from_name=segment.from_waypoint.name,
                to_name=segment.to_waypoint.name,
                distance=segment.selected.distance_m,
                duration=segment.selected.duration_s,
                status=_review_status(segment),
            )
        )
    lines.extend(["", "## 道路步骤", ""])
    for segment in segments:
        lines.append(f"### {segment.segment_id}")
        for step in segment.selected.steps:
            lines.append(
                f"- `{step.road_class.value}` {step.road_name or '未命名道路'} — {step.distance_m} m"
            )
        if segment.reviews:
            lines.append("- 待处理复核项：")
            lines.extend(
                f"  - [{item.severity}] `{item.code}`：{item.message}"
                for item in segment.reviews
            )
        else:
            lines.append("- 无自动生成的复核项。")
        lines.append("")
    return "\n".join(lines)


def _position(point: Coordinate) -> list[float]:
    wgs84 = gcj02_to_wgs84(point)
    return [wgs84.lon, wgs84.lat]


def _step_properties(segment: PlannedSegment, step: RouteStep) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "day": segment.rule.day,
        "from_name": segment.from_waypoint.name,
        "to_name": segment.to_waypoint.name,
        "road_name": step.road_name,
        "road_class": step.road_class.value,
        "distance_m": step.distance_m,
        "segment_duration_s": segment.selected.duration_s,
        "risk_tags": sorted(step.risk_tags),
        "review_status": _review_status(segment),
        "optional_branch": _is_optional(segment),
    }


def _is_optional(segment: PlannedSegment) -> bool:
    return not (
        segment.from_waypoint.include_in_main_totals
        and segment.to_waypoint.include_in_main_totals
    )


def _review_status(segment: PlannedSegment) -> str:
    if any(not step.polyline_gcj for step in segment.selected.steps):
        return "unresolved"
    if segment.reviews:
        return "review_required"
    return "approved"


def _totals(segments: Iterable[PlannedSegment]) -> dict[str, object]:
    materialized = tuple(segments)
    distances = {road_class.value: 0 for road_class in RoadClass}
    for segment in materialized:
        for step in segment.selected.steps:
            distances[step.road_class.value] += step.distance_m
    distance_m = sum(segment.selected.distance_m for segment in materialized)
    baseline_distance_m = sum(segment.baseline_distance_m for segment in materialized)
    unresolved_count = sum(
        1
        for segment in materialized
        if segment.reviews
        or not segment.selected.steps
        or any(not step.polyline_gcj for step in segment.selected.steps)
    )
    return {
        "segment_count": len(materialized),
        "distance_m": distance_m,
        "duration_s": sum(segment.selected.duration_s for segment in materialized),
        "baseline_distance_m": baseline_distance_m,
        "detour_ratio": distance_m / baseline_distance_m if baseline_distance_m else None,
        "unresolved_count": unresolved_count,
        "national_distance_m": distances[RoadClass.NATIONAL.value],
        "provincial_distance_m": distances[RoadClass.PROVINCIAL.value],
        "county_distance_m": distances[RoadClass.COUNTY.value],
        "cycleway_distance_m": distances[RoadClass.CYCLEWAY.value],
        "unknown_distance_m": distances[RoadClass.UNKNOWN.value],
        "city_distance_m": distances[RoadClass.CITY.value],
    }
