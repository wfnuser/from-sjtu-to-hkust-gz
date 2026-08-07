"""Loading and validating the declarative coastal route configuration."""

import json
import re
from pathlib import Path
from typing import Any

from .models import Coordinate, OptionalBranch, RouteConfig, SegmentRule, Waypoint


_CHINESE_CHARACTER = re.compile(r"[\u4e00-\u9fff]")
_REQUIRED_WAYPOINT_FIELDS = ("id", "name", "city", "query")
_REQUIRED_MAIN_START = "上海交通大学闵行校区"
_REQUIRED_MAIN_END = "香港科技大学（广州）"


def load_route_config(path: Path) -> RouteConfig:
    """Load a route configuration while enforcing planning safety invariants."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Unable to read route configuration: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid route configuration JSON: {path}") from error

    if not isinstance(payload, dict):
        raise ValueError("Route configuration must be a JSON object")

    max_detour_ratio = payload.get("max_detour_ratio")
    if isinstance(max_detour_ratio, bool) or max_detour_ratio != 1.15:
        raise ValueError("max_detour_ratio must be exactly 1.15")

    main_waypoints = _parse_waypoints(payload.get("waypoints"), "main route")
    if len(main_waypoints) < 2:
        raise ValueError("Main route must contain both endpoints")
    for waypoint in main_waypoints:
        if not _CHINESE_CHARACTER.search(waypoint.name):
            raise ValueError("Main waypoint display names must contain Chinese characters")
    if main_waypoints[0].name != _REQUIRED_MAIN_START:
        raise ValueError(f"Main route must start at {_REQUIRED_MAIN_START}")
    if main_waypoints[-1].name != _REQUIRED_MAIN_END:
        raise ValueError(f"Main route must end at {_REQUIRED_MAIN_END}")

    checkin_waypoints = _parse_waypoints(
        payload.get("checkin_waypoints", []), "check-in route"
    )
    segment_rules = _parse_segment_rules(payload.get("segment_rules", {}))
    optional_branches = _parse_optional_branches(payload.get("optional_branches", {}))

    route_id = _required_string(payload, "route_id", "route configuration")
    return RouteConfig(
        route_id=route_id,
        max_detour_ratio=max_detour_ratio,
        waypoints=main_waypoints,
        checkin_waypoints=checkin_waypoints,
        segment_rules=segment_rules,
        optional_branches=optional_branches,
    )


def _parse_waypoints(value: Any, context: str) -> tuple[Waypoint, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{context} waypoints must be a list")
    return tuple(_parse_waypoint(item, context) for item in value)


def _parse_waypoint(value: Any, context: str) -> Waypoint:
    if not isinstance(value, dict):
        raise ValueError(f"{context} waypoint must be an object")
    for field in _REQUIRED_WAYPOINT_FIELDS:
        _required_string(value, field, f"{context} waypoint")

    coordinate = _parse_coordinate(value.get("coordinate"), context)
    return Waypoint(
        id=value["id"],
        name=value["name"],
        city=value["city"],
        query=value["query"],
        coordinate=coordinate,
        required=_optional_bool(value, "required", True, context),
        include_in_main_totals=_optional_bool(
            value, "include_in_main_totals", True, context
        ),
        branch=_optional_string(value, "branch", "main", context),
    )


def _parse_coordinate(value: Any, context: str) -> Coordinate | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{context} coordinate must be null or an object")
    lon = value.get("lon")
    lat = value.get("lat")
    if not _is_number(lon) or not _is_number(lat):
        raise ValueError(f"{context} coordinate requires numeric lon and lat")
    return Coordinate(lon=float(lon), lat=float(lat))


def _parse_segment_rules(value: Any) -> dict[str, SegmentRule]:
    if not isinstance(value, dict):
        raise ValueError("segment_rules must be an object")

    rules: dict[str, SegmentRule] = {}
    for segment_id, item in value.items():
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError("segment rule identifiers must be non-empty strings")
        if not isinstance(item, dict):
            raise ValueError(f"Segment rule {segment_id} must be an object")
        anchors = item.get("anchor_queries", [])
        if not isinstance(anchors, list) or not all(
            isinstance(anchor, str) and anchor for anchor in anchors
        ):
            raise ValueError(f"Segment rule {segment_id} anchors must be non-empty strings")
        allowed_national_m = item.get("allowed_national_m", 0)
        if not isinstance(allowed_national_m, int) or isinstance(
            allowed_national_m, bool
        ):
            raise ValueError(f"Segment rule {segment_id} allowed_national_m must be an integer")
        day = item.get("day")
        if day is not None and (not isinstance(day, int) or isinstance(day, bool)):
            raise ValueError(f"Segment rule {segment_id} day must be an integer or null")
        national_exception_reason = item.get("national_exception_reason", "")
        if not isinstance(national_exception_reason, str):
            raise ValueError(
                f"Segment rule {segment_id} national_exception_reason must be a string"
            )
        rules[segment_id] = SegmentRule(
            segment_id=_optional_string(item, "segment_id", segment_id, "segment rule"),
            anchor_queries=tuple(anchors),
            parallel_road_available=_optional_bool(
                item, "parallel_road_available", False, "segment rule"
            ),
            allowed_national_m=allowed_national_m,
            day=day,
            national_exception_reason=national_exception_reason,
        )
    return rules


def _parse_optional_branches(value: Any) -> dict[str, OptionalBranch]:
    if not isinstance(value, dict):
        raise ValueError("optional_branches must be an object")

    branches: dict[str, OptionalBranch] = {}
    for branch_id, item in value.items():
        if not isinstance(branch_id, str) or not branch_id:
            raise ValueError("optional branch identifiers must be non-empty strings")
        if not isinstance(item, dict):
            raise ValueError(f"Optional branch {branch_id} must be an object")
        enabled = _optional_bool(item, "enabled", False, "optional branch")
        if enabled:
            raise ValueError(f"Optional branch {branch_id} must be disabled")
        branches[branch_id] = OptionalBranch(
            name=_optional_string(item, "name", branch_id, "optional branch"),
            enabled=enabled,
            waypoints=_parse_waypoints(item.get("waypoints", []), f"optional branch {branch_id}"),
        )
    return branches


def _required_string(value: dict[str, Any], field: str, context: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{context} requires a non-empty {field}")
    return result


def _optional_string(value: dict[str, Any], field: str, default: str, context: str) -> str:
    if field not in value:
        return default
    return _required_string(value, field, context)


def _optional_bool(value: dict[str, Any], field: str, default: bool, context: str) -> bool:
    if field not in value:
        return default
    result = value[field]
    if not isinstance(result, bool):
        raise ValueError(f"{context} {field} must be a boolean")
    return result


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
