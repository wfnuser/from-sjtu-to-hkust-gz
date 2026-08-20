"""Loading and validating declarative route configurations."""

import json
import re
from pathlib import Path
from typing import Any

from .models import (
    Coordinate,
    OptionalBranch,
    RouteConfig,
    SegmentRule,
    VerifiedSafeStep,
    Waypoint,
)


_CHINESE_CHARACTER = re.compile(r"[\u4e00-\u9fff]")
_REQUIRED_WAYPOINT_FIELDS = ("id", "name", "city", "query")
_REQUIRED_MAIN_START = "上海交通大学闵行校区"
_REQUIRED_MAIN_END = "香港科技大学（广州）"
_INLAND_ROUTE_ID = "inland-main"
_EXECUTION_ROUTE_ID = "inland-execution"
_REROUTE_STATUSES = frozenset({"unreviewed", "adopted", "rejected", "manual_review"})
_INLAND_MAIN_CORRIDOR = (
    "阳曲路",
    "上海交通大学附属中学本部",
    "bilibili 国正中心",
    "大连路地铁站",
    "昌化路649号",
    "京东上海（中海中心）职场",
    "阿里中心（虹桥）",
    "上海交通大学闵行校区",
    "漕泾数字游民国际村",
    "海盐",
    "海宁",
    "杭州阿里巴巴总部",
    "桐庐",
    "建德之江村",
    "龙游",
    "衢州",
    "玉山",
    "上饶",
    "鹰潭",
    "抚州",
    "南城",
    "广昌",
    "宁都",
    "于都",
    "赣州",
    "信丰",
    "龙南",
    "定南",
    "和平",
    "河源",
    "博罗",
    "增城",
    "番禺",
    "香港科技大学（广州）",
)

_INLAND_EXECUTION_CORRIDOR = (
    "阳曲路",
    "上海交通大学附属中学本部",
    "bilibili 国正中心",
    "大连路地铁站",
    "昌化路649号",
    "京东上海（中海中心）职场",
    "阿里中心（虹桥）",
    "上海交通大学闵行校区",
    "叶新公路东段",
    "叶新公路西段",
    "桐乡万象汇振兴西路亚朵酒店",
    "阿里巴巴西溪园区",
    "杭州未来科技城海创园地铁站亚朵酒店",
    "捷安特自行车（桐庐店）",
    "麗枫酒店（杭州建德新安江店）",
    "常山东方广场酒店",
    "维也纳国际酒店（上饶经开区店）",
    "鹰潭枫丹白露酒店（雲锦君澜）",
    "维也纳酒店（南城店）",
    "富源大酒店（广昌头陂镇）",
    "于都锦汇酒店（葛坳乡）",
    "枕山月酒店（韩坊镇）",
    "定南格兰云天国际酒店",
    "亚瓦酒店（漳溪畲族乡）",
    "博罗云鹏酒店（麻陂镇）",
    "广州增城荔湖木莲庄酒店",
    "香港科技大学（广州）",
)


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

    route_id = _required_string(payload, "route_id", "route configuration")
    max_detour_ratio = payload.get("max_detour_ratio")
    if isinstance(max_detour_ratio, bool) or max_detour_ratio != 1.15:
        raise ValueError("max_detour_ratio must be exactly 1.15")

    main_waypoints = _parse_waypoints(payload.get("waypoints"), "main route")
    if len(main_waypoints) < 2:
        raise ValueError("Main route must contain both endpoints")
    for waypoint in main_waypoints:
        if not _CHINESE_CHARACTER.search(waypoint.name):
            raise ValueError("Main waypoint display names must contain Chinese characters")
    required_start = (
        _INLAND_MAIN_CORRIDOR[0]
        if route_id in {_INLAND_ROUTE_ID, _EXECUTION_ROUTE_ID}
        else _REQUIRED_MAIN_START
    )
    if main_waypoints[0].name != required_start:
        raise ValueError(f"Main route must start at {required_start}")
    if main_waypoints[-1].name != _REQUIRED_MAIN_END:
        raise ValueError(f"Main route must end at {_REQUIRED_MAIN_END}")
    if route_id == _INLAND_ROUTE_ID:
        _validate_inland_main_corridor(main_waypoints)
    elif route_id == _EXECUTION_ROUTE_ID:
        _validate_execution_corridor(main_waypoints)

    checkin_waypoints = _parse_waypoints(
        payload.get("checkin_waypoints", []), "check-in route"
    )
    segment_rules = _parse_segment_rules(payload.get("segment_rules", {}))
    optional_branches = _parse_optional_branches(payload.get("optional_branches", {}))

    return RouteConfig(
        route_id=route_id,
        max_detour_ratio=max_detour_ratio,
        waypoints=main_waypoints,
        checkin_waypoints=checkin_waypoints,
        segment_rules=segment_rules,
        optional_branches=optional_branches,
    )


def _validate_inland_main_corridor(waypoints: tuple[Waypoint, ...]) -> None:
    if tuple(waypoint.name for waypoint in waypoints) != _INLAND_MAIN_CORRIDOR:
        raise ValueError("inland-main corridor must match the bound inland waypoint order")
    if any(waypoint.coordinate is not None for waypoint in waypoints):
        raise ValueError("inland-main corridor coordinates must be null before resolution")


def _validate_execution_corridor(waypoints: tuple[Waypoint, ...]) -> None:
    if tuple(waypoint.name for waypoint in waypoints) != _INLAND_EXECUTION_CORRIDOR:
        raise ValueError("inland-execution corridor must match the bound execution order")
    if any(waypoint.coordinate is not None for waypoint in waypoints):
        raise ValueError("inland-execution coordinates must be null before resolution")


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
        parallel_road_max_extra_m = item.get("parallel_road_max_extra_m", 0)
        if (
            not isinstance(parallel_road_max_extra_m, int)
            or isinstance(parallel_road_max_extra_m, bool)
            or parallel_road_max_extra_m < 0
            or parallel_road_max_extra_m > 2_000
        ):
            raise ValueError(
                f"Segment rule {segment_id} parallel_road_max_extra_m must be a non-negative integer at most 2000"
            )
        verified_safe_steps_value = item.get("verified_safe_steps", [])
        if not isinstance(verified_safe_steps_value, list):
            raise ValueError(
                f"Segment rule {segment_id} verified_safe_steps must be a list"
            )
        verified_safe_steps: list[VerifiedSafeStep] = []
        for verified_step in verified_safe_steps_value:
            if not isinstance(verified_step, dict):
                raise ValueError(
                    f"Segment rule {segment_id} verified_safe_steps must contain objects"
                )
            road_name = verified_step.get("road_name")
            max_distance_m = verified_step.get("max_distance_m")
            evidence_url = verified_step.get("evidence_url")
            evidence_note = verified_step.get("evidence_note")
            if (
                not isinstance(road_name, str)
                or not road_name.strip()
                or not isinstance(max_distance_m, int)
                or isinstance(max_distance_m, bool)
                or max_distance_m <= 0
                or not isinstance(evidence_url, str)
                or not evidence_url.startswith("https://")
                or not isinstance(evidence_note, str)
                or not evidence_note.strip()
            ):
                raise ValueError(
                    f"Segment rule {segment_id} verified_safe_steps entries require a road name, positive distance, HTTPS evidence, and note"
                )
            verified_safe_steps.append(
                VerifiedSafeStep(
                    road_name.strip(),
                    max_distance_m,
                    evidence_url,
                    evidence_note.strip(),
                )
            )
        allowed_hard_risk_m = item.get("allowed_hard_risk_m", 0)
        if (
            not isinstance(allowed_hard_risk_m, int)
            or isinstance(allowed_hard_risk_m, bool)
            or allowed_hard_risk_m < 0
        ):
            raise ValueError(
                f"Segment rule {segment_id} allowed_hard_risk_m must be a non-negative integer"
            )
        day = item.get("day")
        if day is not None and (not isinstance(day, int) or isinstance(day, bool)):
            raise ValueError(f"Segment rule {segment_id} day must be an integer or null")
        national_exception_reason = item.get("national_exception_reason", "")
        if not isinstance(national_exception_reason, str):
            raise ValueError(
                f"Segment rule {segment_id} national_exception_reason must be a string"
            )
        hard_risk_exception_reason = item.get("hard_risk_exception_reason", "")
        if not isinstance(hard_risk_exception_reason, str):
            raise ValueError(
                f"Segment rule {segment_id} hard_risk_exception_reason must be a string"
            )
        if allowed_hard_risk_m and not hard_risk_exception_reason.strip():
            raise ValueError(
                f"Segment rule {segment_id} hard_risk_exception_reason is required"
            )
        if not allowed_hard_risk_m and hard_risk_exception_reason.strip():
            raise ValueError(
                f"Segment rule {segment_id} hard_risk_exception_reason requires an allowance"
            )
        reroute_status = item.get("reroute_status", "unreviewed")
        if reroute_status not in _REROUTE_STATUSES:
            raise ValueError(
                f"Segment rule {segment_id} reroute_status must be a reviewed status"
            )
        reroute_reason = item.get("reroute_reason", "")
        if not isinstance(reroute_reason, str):
            raise ValueError(f"Segment rule {segment_id} reroute_reason must be a string")
        if reroute_status == "unreviewed" and reroute_reason.strip():
            raise ValueError(
                f"Segment rule {segment_id} reroute_reason requires a reviewed status"
            )
        if reroute_status != "unreviewed" and not reroute_reason.strip():
            raise ValueError(
                f"Segment rule {segment_id} reroute_reason is required for a reviewed status"
            )
        preferred_candidate_index = item.get("preferred_candidate_index")
        if preferred_candidate_index is not None and (
            not isinstance(preferred_candidate_index, int)
            or isinstance(preferred_candidate_index, bool)
            or not 0 <= preferred_candidate_index <= 2
        ):
            raise ValueError(
                f"Segment rule {segment_id} preferred_candidate_index must be 0, 1, 2, or null"
            )
        rules[segment_id] = SegmentRule(
            segment_id=_optional_string(item, "segment_id", segment_id, "segment rule"),
            anchor_queries=tuple(anchors),
            parallel_road_available=_optional_bool(
                item, "parallel_road_available", False, "segment rule"
            ),
            parallel_road_max_extra_m=parallel_road_max_extra_m,
            verified_safe_steps=tuple(verified_safe_steps),
            allowed_national_m=allowed_national_m,
            allowed_hard_risk_m=allowed_hard_risk_m,
            day=day,
            national_exception_reason=national_exception_reason,
            hard_risk_exception_reason=hard_risk_exception_reason,
            reroute_status=reroute_status,
            reroute_reason=reroute_reason,
            preferred_candidate_index=preferred_candidate_index,
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
