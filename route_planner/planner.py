"""Safety-first planning of direct baselines and explicitly anchored sublegs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from route_planner.coordinates import select_unique_candidate
from route_planner.models import (
    CandidateRoute,
    Coordinate,
    GeocodeCandidate,
    PlannedSegment,
    ReviewItem,
    SegmentRule,
    Waypoint,
)
from route_planner.roads import ReviewRequired, candidate_metrics, choose_candidate


class PlanningClient(Protocol):
    def geocode(self, query: str, city: str) -> tuple[GeocodeCandidate, ...]: ...

    def electrobike(
        self, origin: Coordinate, destination: Coordinate, alternatives: int = 3
    ) -> tuple[CandidateRoute, ...]: ...


class RoutePlanner:
    def __init__(self, client: PlanningClient):
        self._client = client

    def plan_segment(
        self, start: Waypoint, end: Waypoint, rule: SegmentRule
    ) -> PlannedSegment:
        """Plan a segment with a shortest direct baseline and selected real sublegs."""
        start_coordinate = _waypoint_coordinate(start, rule.segment_id)
        end_coordinate = _waypoint_coordinate(end, rule.segment_id)
        direct_candidates = self._client.electrobike(start_coordinate, end_coordinate)
        baseline = _shortest_candidate(direct_candidates, rule.segment_id)
        if baseline.distance_m == 0:
            raise ReviewRequired(rule.segment_id, ("direct baseline has zero distance",))

        anchor_coordinates = tuple(
            _resolve_anchor(
                self._client,
                *_anchor_locality(anchor_query, start.city),
                rule.segment_id,
            )
            for anchor_query in rule.anchor_queries
        )
        if anchor_coordinates:
            selected_sublegs = _select_sublegs(
                self._client,
                (start_coordinate, *anchor_coordinates, end_coordinate),
                rule,
            )
        else:
            selected_sublegs = (choose_candidate(direct_candidates, rule),)

        _require_real_polylines(selected_sublegs, rule.segment_id)
        selected = CandidateRoute(
            source_index=0,
            distance_m=sum(subleg.distance_m for subleg in selected_sublegs),
            duration_s=sum(subleg.duration_s for subleg in selected_sublegs),
            steps=tuple(step for subleg in selected_sublegs for step in subleg.steps),
        )
        subleg_distances_m = tuple(subleg.distance_m for subleg in selected_sublegs)
        subleg_durations_s = tuple(subleg.duration_s for subleg in selected_sublegs)
        detour_ratio = selected.distance_m / baseline.distance_m
        reviews = _reviews(rule, selected, detour_ratio, subleg_distances_m)
        return PlannedSegment(
            segment_id=rule.segment_id,
            from_waypoint=start,
            to_waypoint=end,
            rule=rule,
            baseline_distance_m=baseline.distance_m,
            selected=selected,
            detour_ratio=detour_ratio,
            subleg_distances_m=subleg_distances_m,
            reviews=reviews,
            subleg_durations_s=subleg_durations_s,
        )


def _waypoint_coordinate(waypoint: Waypoint, segment_id: str) -> Coordinate:
    if waypoint.coordinate is None:
        raise ReviewRequired(segment_id, (f"unresolved waypoint: {waypoint.query}",))
    return waypoint.coordinate


def _shortest_candidate(
    candidates: Sequence[CandidateRoute], segment_id: str
) -> CandidateRoute:
    if not candidates:
        raise ReviewRequired(segment_id, ("no direct baseline candidates",))
    return min(candidates, key=lambda candidate: (candidate.distance_m, candidate.duration_s, candidate.source_index))


def _resolve_anchor(
    client: PlanningClient, query: str, city: str, segment_id: str
) -> Coordinate:
    candidate = select_unique_candidate(query, city, client.geocode(query, city))
    if candidate is None:
        raise ReviewRequired(segment_id, (f"unresolved or ambiguous anchor: {query}",))
    return candidate.location_gcj


def _anchor_locality(value: str, default_city: str) -> tuple[str, str]:
    if "::" not in value:
        return value, default_city
    city, query = value.split("::", 1)
    if not city or not query:
        raise ValueError("Anchor locality must be 城市::查询")
    return query, city


def _select_sublegs(
    client: PlanningClient,
    points: tuple[Coordinate, ...],
    rule: SegmentRule,
) -> tuple[CandidateRoute, ...]:
    return tuple(
        choose_candidate(client.electrobike(origin, destination), rule)
        for origin, destination in zip(points, points[1:])
    )


def _require_real_polylines(
    sublegs: Sequence[CandidateRoute], segment_id: str
) -> None:
    if (
        not sublegs
        or any(not subleg.steps for subleg in sublegs)
        or any(not step.polyline_gcj for subleg in sublegs for step in subleg.steps)
    ):
        raise ReviewRequired(segment_id, ("selected route lacks a real API polyline",))


def _reviews(
    rule: SegmentRule,
    selected: CandidateRoute,
    detour_ratio: float,
    subleg_distances_m: Sequence[int],
) -> tuple[ReviewItem, ...]:
    segment_id = rule.segment_id
    reviews: list[ReviewItem] = []
    if detour_ratio > 1.15:
        reviews.append(
            ReviewItem(
                "DETOUR_OVER_15_PERCENT",
                segment_id,
                "warning",
                "Anchored route exceeds the 15% detour limit.",
            )
        )
    for distance_m in subleg_distances_m:
        if distance_m > 80_000:
            reviews.append(
                ReviewItem(
                    "SUBLEG_OVER_80_KM",
                    segment_id,
                    "warning",
                    "Subleg exceeds 80 km; add a real town or road anchor.",
                    distance_m=distance_m,
                )
            )
    national_m = candidate_metrics(selected).national_m
    if (
        national_m
        and national_m <= rule.allowed_national_m
        and rule.national_exception_reason.strip()
    ):
        reviews.append(
            ReviewItem(
                "NATIONAL_ROAD_EXCEPTION_APPROVED",
                segment_id,
                "info",
                rule.national_exception_reason.strip(),
                distance_m=national_m,
            )
        )
    return tuple(reviews)
