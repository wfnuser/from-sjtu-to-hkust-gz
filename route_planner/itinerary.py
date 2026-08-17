"""Merge an explicit day contract with published execution-route artifacts."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any


def build_itinerary(
    day_config: dict[str, Any],
    manifest: dict[str, Any],
    geojson: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return derived day summaries and GeoJSON tagged with one execution day."""
    route_id = _string(day_config, "route_id")
    if _string(manifest, "route_id") != route_id:
        raise ValueError("Itinerary and manifest route IDs must match.")

    days = deepcopy(_list(day_config, "days"))
    start_date = _optional_date(day_config, "start_date")
    segments = _list(manifest, "segments")
    ordered_ids = [_string(segment, "segment_id") for segment in segments]
    assigned_ids = [
        segment_id
        for day in days
        for segment_id in _string_list(day, "segments")
    ]
    if assigned_ids != ordered_ids or len(assigned_ids) != len(set(assigned_ids)):
        raise ValueError("Itinerary must assign every manifest segment exactly once in route order.")

    segment_days: dict[str, int] = {}
    segment_metrics: dict[str, tuple[int, int]] = {}
    for segment in segments:
        segment_id = _string(segment, "segment_id")
        selected = _object(segment, "selected")
        segment_metrics[segment_id] = (
            _integer(selected, "distance_m"),
            _integer(selected, "duration_s"),
        )

    for day in days:
        day_id = _integer(day, "day")
        if start_date is not None:
            day["date"] = (start_date + timedelta(days=day_id)).isoformat()
        ids = _string_list(day, "segments")
        distance_m = sum(segment_metrics[segment_id][0] for segment_id in ids)
        duration_s = sum(segment_metrics[segment_id][1] for segment_id in ids)
        day["distance_m"] = distance_m
        day["duration_s"] = duration_s
        day["long_day"] = distance_m > 145_000
        for segment_id in ids:
            segment_days[segment_id] = day_id

    display_start_day = _optional_integer(day_config, "display_start_day", 0)
    remaining_start_day = _optional_integer(day_config, "remaining_start_day", 3)
    public_days = [
        day for day in days if _integer(day, "day") >= display_start_day
    ]
    remaining_days = [
        day
        for day in days
        if _integer(day, "day") >= remaining_start_day and _string_list(day, "segments")
    ]
    remaining_distance_m = sum(_integer(day, "distance_m") for day in remaining_days)
    itinerary = {
        "route_id": route_id,
        "days": days,
        "segment_days": segment_days,
        "display_start_day": display_start_day,
        "remaining_start_day": remaining_start_day,
        "total_distance_m": sum(_integer(day, "distance_m") for day in days),
        "public_total_distance_m": sum(_integer(day, "distance_m") for day in public_days),
        "remaining_distance_m": remaining_distance_m,
        "average_riding_distance_m": round(remaining_distance_m / len(remaining_days))
        if remaining_days
        else 0,
    }
    if start_date is not None:
        itinerary["start_date"] = start_date.isoformat()

    tagged = deepcopy(geojson)
    for feature in _list(tagged, "features"):
        properties = _object(feature, "properties")
        segment_id = _string(properties, "segment_id")
        try:
            properties["day_id"] = segment_days[segment_id]
        except KeyError as error:
            raise ValueError("GeoJSON contains a segment absent from the itinerary.") from error
    return itinerary, tagged


def _object(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"{key} must be an object")
    return item


def _list(value: dict[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise ValueError(f"{key} must be a list")
    return item


def _string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{key} must be a non-empty string")
    return item


def _integer(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key} must be an integer")
    return item


def _optional_integer(value: dict[str, Any], key: str, default: int) -> int:
    item = value.get(key, default)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key} must be an integer")
    return item


def _optional_date(value: dict[str, Any], key: str) -> date | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError(f"{key} must be an ISO date")
    try:
        return date.fromisoformat(item)
    except ValueError as error:
        raise ValueError(f"{key} must be an ISO date") from error


def _string_list(value: dict[str, Any], key: str) -> list[str]:
    items = _list(value, key)
    if not all(isinstance(item, str) and item for item in items):
        raise ValueError(f"{key} must contain strings")
    return items
