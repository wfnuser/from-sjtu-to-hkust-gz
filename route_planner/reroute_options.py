"""GeoJSON export for optional safety detours alongside the published route."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from route_planner.coordinates import gcj02_to_wgs84
from route_planner.models import Coordinate, PlannedSegment
from route_planner.roads import candidate_metrics


@dataclass(frozen=True)
class RerouteOption:
    candidate_id: str
    label: str
    current: PlannedSegment
    proposed: PlannedSegment
    decision: str = "manual_review"


def build_reroute_options(options: Sequence[RerouteOption]) -> dict[str, object]:
    """Export alternative geometry plus compact original/alternative comparisons."""
    summaries: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    for option in options:
        current_metrics = candidate_metrics(option.current.selected)
        proposed_metrics = candidate_metrics(option.proposed.selected)
        distance_delta_m = (
            option.proposed.selected.distance_m - option.current.selected.distance_m
        )
        duration_delta_s = (
            option.proposed.selected.duration_s - option.current.selected.duration_s
        )
        national_reduction_m = current_metrics.national_m - proposed_metrics.national_m
        summary = {
            "segment_id": option.current.segment_id,
            "candidate_id": option.candidate_id,
            "label": option.label,
            "from_name": option.current.from_waypoint.name,
            "to_name": option.current.to_waypoint.name,
            "current_distance_m": option.current.selected.distance_m,
            "current_duration_s": option.current.selected.duration_s,
            "current_national_m": current_metrics.national_m,
            "alternative_distance_m": option.proposed.selected.distance_m,
            "alternative_duration_s": option.proposed.selected.duration_s,
            "alternative_national_m": proposed_metrics.national_m,
            "alternative_unknown_m": proposed_metrics.unknown_m,
            "distance_delta_m": distance_delta_m,
            "duration_delta_s": duration_delta_s,
            "national_reduction_m": national_reduction_m,
            "review_status": (
                "recommended" if option.decision == "candidate" else "manual_review"
            ),
        }
        summaries.append(summary)
        for step_index, step in enumerate(option.proposed.selected.steps):
            if len(step.polyline_gcj) < 2:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [_position(point) for point in step.polyline_gcj],
                    },
                    "properties": {
                        **summary,
                        "step_index": step_index,
                        "road_name": step.road_name,
                        "road_class": step.road_class.value,
                        "step_distance_m": step.distance_m,
                        "risk_tags": sorted(step.risk_tags),
                        "route_role": "alternative",
                    },
                }
            )
    return {"type": "FeatureCollection", "options": summaries, "features": features}


def _position(point: Coordinate) -> list[float]:
    converted = gcj02_to_wgs84(point)
    return [converted.lon, converted.lat]
