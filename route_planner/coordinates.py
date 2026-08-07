"""Coordinate conversion and conservative AMap POI resolution."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from route_planner.models import (
    Coordinate,
    GeocodeCandidate,
    PoiResolution,
    ResolutionReport,
    RouteConfig,
)


class GeocodingClient(Protocol):
    def geocode(self, query: str, city: str) -> tuple[GeocodeCandidate, ...]: ...


def parse_polyline(value: str) -> tuple[Coordinate, ...]:
    """Parse an AMap ``longitude,latitude;...`` polyline without reordering it."""
    if not isinstance(value, str) or not value:
        raise ValueError("Polyline must be a non-empty string")

    coordinates = tuple(_parse_coordinate(part) for part in value.split(";"))
    if not coordinates:
        raise ValueError("Polyline must contain at least one coordinate")
    return coordinates


def gcj02_to_wgs84(point: Coordinate) -> Coordinate:
    """Convert a GCJ-02 coordinate to WGS84 using the public offset algorithm."""
    if _outside_china(point):
        return point

    delta_lat = _transform_lat(point.lon - 105.0, point.lat - 35.0)
    delta_lon = _transform_lon(point.lon - 105.0, point.lat - 35.0)
    rad_lat = point.lat / 180.0 * math.pi
    magic = 1 - _EE * math.sin(rad_lat) ** 2
    sqrt_magic = math.sqrt(magic)
    delta_lat = (delta_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    delta_lon = (delta_lon * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return Coordinate(lon=point.lon - delta_lon, lat=point.lat - delta_lat)


def resolve_waypoints(config: RouteConfig, client: GeocodingClient) -> ResolutionReport:
    """Resolve main-route POIs, retaining ambiguity for manual review."""
    resolutions = tuple(
        _resolve_one(waypoint.query, waypoint.city, client.geocode(waypoint.query, waypoint.city))
        for waypoint in config.waypoints
    )
    return ResolutionReport(
        resolutions=resolutions,
        unresolved_queries=tuple(
            resolution.query for resolution in resolutions if resolution.selected is None
        ),
    )


def select_unique_candidate(
    query: str, city: str, candidates: Sequence[GeocodeCandidate]
) -> GeocodeCandidate | None:
    """Return a candidate only when the API produced one exact, local match."""
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if candidate.name != query or not _matches_city(candidate, city):
        return None
    return candidate


def _resolve_one(
    query: str, city: str, candidates: tuple[GeocodeCandidate, ...]
) -> PoiResolution:
    return PoiResolution(
        query=query,
        city=city,
        candidates=candidates,
        selected=select_unique_candidate(query, city, candidates),
    )


def _matches_city(candidate: GeocodeCandidate, city: str) -> bool:
    expected = city.strip()
    if not expected:
        return False
    return expected in candidate.formatted_address or expected in candidate.district


def _parse_coordinate(value: str) -> Coordinate:
    parts = value.split(",")
    if len(parts) != 2:
        raise ValueError("Polyline coordinate must be longitude,latitude")
    try:
        lon, lat = (float(part) for part in parts)
    except ValueError as error:
        raise ValueError("Polyline coordinate must be numeric") from error
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError("Polyline coordinate must be finite")
    return Coordinate(lon=lon, lat=lat)


def _outside_china(point: Coordinate) -> bool:
    return not (72.004 <= point.lon <= 137.8347 and 0.8293 <= point.lat <= 55.8271)


def _transform_lat(lon: float, lat: float) -> float:
    result = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat**2 + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
    result += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
    result += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    return result + (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0


def _transform_lon(lon: float, lat: float) -> float:
    result = 300.0 + lon + 2.0 * lat + 0.1 * lon**2 + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
    result += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
    result += (20.0 * math.sin(lon * math.pi) + 40.0 * math.sin(lon / 3.0 * math.pi)) * 2.0 / 3.0
    return result + (150.0 * math.sin(lon / 12.0 * math.pi) + 300.0 * math.sin(lon / 30.0 * math.pi)) * 2.0 / 3.0


_A = 6378245.0
_EE = 0.00669342162296594323
