"""Stable GeoJSON and human-review exports for planned route segments."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from route_planner.coordinates import gcj02_to_wgs84
from route_planner.models import Coordinate, PlannedSegment, RoadClass, RouteStep
from route_planner.roads import effective_risk_tags


_BRANCH_IDS = frozenset({"main", "ningbo", "shenzhen"})
_DEADLINE_START = date(2026, 8, 13)
_DEADLINE_END = date(2026, 8, 30)
_REQUIRED_WORK_HOURS_PER_DAY = 4
_MAX_RIDING_HOURS_PER_DAY = 6
_MAX_RIDING_DAYS_BY_PROFILE = {
    "coastal": 15,
    "inland": 15,
    "execution": 16,
}


def build_geojson(
    segments: Sequence[PlannedSegment], *, profile: str = "coastal"
) -> dict[str, object]:
    """Return one WGS84 LineString feature for every API road step with geometry."""
    features: list[dict[str, object]] = []
    _, segment_days = _day_summaries(
        tuple(segment for segment in segments if not _is_optional(segment)), profile
    )
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
                    "properties": _step_properties(
                        segment, step, segment_days.get(segment.segment_id, [])
                    ),
                }
            )
    return {"type": "FeatureCollection", "features": features}


def build_summary(
    segments: Sequence[PlannedSegment],
    max_detour_ratio: float,
    quota_limited_probes: Sequence[str] = (),
    *,
    profile: str = "coastal",
) -> dict[str, object]:
    """Summarize main-route totals separately from optional branches."""
    main = tuple(segment for segment in segments if not _is_optional(segment))
    optional = tuple(segment for segment in segments if _is_optional(segment))
    main_totals = _totals(main)
    days, segment_days = _day_summaries(main, profile)
    schedule = _schedule_contract(days, profile)
    distance_m = int(main_totals["distance_m"])
    unknown_m = int(main_totals["unknown_distance_m"])
    blank_name_m = sum(
        step.distance_m
        for segment in main
        for step in segment.selected.steps
        if not step.road_name.strip()
    )
    return {
        "publication_status": "provisional_road_level_review_required",
        "max_detour_ratio": max_detour_ratio,
        "main": main_totals,
        "days": days,
        "segment_days": segment_days,
        "schedule": {
            "day_count": len(days),
            "target_distance_m": [80_000, 120_000],
            "target_duration_s": [14_400, 21_600],
            "max_duration_s": 21_600,
            **schedule,
        },
        "limitations": {
            "road_level_status": "provisional",
            "unknown_distance_m": unknown_m,
            "unknown_percent": round(unknown_m * 100 / distance_m, 2) if distance_m else 0.0,
            "blank_name_distance_m": blank_name_m,
            "quota_limited_probes": list(quota_limited_probes),
            "automatic_checks_are_not_road_level_verification": True,
        },
        "all_branches": _totals(segments),
        "optional_branch_excluded": _totals(optional),
    }


def _practical_day_summaries(
    segments: Sequence[PlannedSegment],
) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
    legs = _itinerary_legs(segments)
    if not legs:
        return [], {}
    boundaries = _minimum_day_boundaries(legs)
    summaries: list[dict[str, object]] = []
    segment_days: dict[str, list[int]] = {}
    for day, (start, end) in enumerate(boundaries, 1):
        day_legs = legs[start:end]
        distance_m = sum(int(leg["distance_m"]) for leg in day_legs)
        duration_s = sum(int(leg["duration_s"]) for leg in day_legs)
        segment_ids = list(dict.fromkeys(str(leg["segment_id"]) for leg in day_legs))
        for segment_id in segment_ids:
            segment_days.setdefault(segment_id, []).append(day)
        summaries.append(
            {
                "day": day,
                "from_name": day_legs[0]["from_name"],
                "to_name": day_legs[-1]["to_name"],
                "distance_m": distance_m,
                "duration_s": duration_s,
                "distance_target_met": 80_000 <= distance_m <= 120_000,
                "duration_target_met": 14_400 <= duration_s <= 21_600,
                "duration_limit_met": duration_s <= 21_600,
                "lodging_network_endpoint": day_legs[-1]["to_name"],
                "lodging_network_status": "named_endpoint_unverified",
                "segment_count": len(segment_ids),
                "segments": segment_ids,
                "legs": [
                    {
                        "segment_id": leg["segment_id"],
                        "subleg_index": leg["subleg_index"],
                    }
                    for leg in day_legs
                ],
            }
        )
    return summaries, segment_days


def _day_summaries(
    segments: Sequence[PlannedSegment], profile: str
) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
    if profile == "execution":
        return _configured_day_summaries(segments)
    return _practical_day_summaries(segments)


def _configured_day_summaries(
    segments: Sequence[PlannedSegment],
) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
    """Summarize execution segments by their explicit itinerary day contract."""
    grouped: dict[int, list[PlannedSegment]] = {}
    previous_day = -1
    for segment in segments:
        day = segment.rule.day
        if not isinstance(day, int) or isinstance(day, bool) or day < 0:
            raise ValueError("Execution segments require a non-negative configured day.")
        if day < previous_day:
            raise ValueError("Execution segment days must be non-decreasing.")
        grouped.setdefault(day, []).append(segment)
        previous_day = day

    summaries: list[dict[str, object]] = []
    segment_days: dict[str, list[int]] = {}
    for day, day_segments in grouped.items():
        distance_m = sum(segment.selected.distance_m for segment in day_segments)
        duration_s = sum(segment.selected.duration_s for segment in day_segments)
        segment_ids = [segment.segment_id for segment in day_segments]
        for segment_id in segment_ids:
            segment_days[segment_id] = [day]
        summaries.append(
            {
                "day": day,
                "from_name": day_segments[0].from_waypoint.name,
                "to_name": day_segments[-1].to_waypoint.name,
                "distance_m": distance_m,
                "duration_s": duration_s,
                "distance_target_met": 80_000 <= distance_m <= 120_000,
                "duration_target_met": 14_400 <= duration_s <= 21_600,
                "duration_limit_met": duration_s <= 21_600,
                "lodging_network_endpoint": day_segments[-1].to_waypoint.name,
                "lodging_network_status": "named_endpoint_unverified",
                "segment_count": len(segment_ids),
                "segments": segment_ids,
                "legs": [
                    {
                        "segment_id": segment.segment_id,
                        "subleg_index": subleg_index,
                    }
                    for segment in day_segments
                    for subleg_index in range(len(segment.subleg_distances_m or (segment.selected.distance_m,)))
                ],
            }
        )
    return summaries, segment_days


def _itinerary_legs(segments: Sequence[PlannedSegment]) -> list[dict[str, object]]:
    legs: list[dict[str, object]] = []
    for segment in segments:
        distances = segment.subleg_distances_m or (segment.selected.distance_m,)
        durations = segment.subleg_durations_s or _proportional_durations(
            distances, segment.selected.duration_s
        )
        if len(distances) != len(durations):
            raise ValueError("Subleg distances and durations must align.")
        names = [
            segment.from_waypoint.name,
            *(query.split("::", 1)[-1] for query in segment.rule.anchor_queries),
            segment.to_waypoint.name,
        ]
        if len(names) != len(distances) + 1:
            raise ValueError("Every subleg needs a named endpoint.")
        for index, (distance_m, duration_s) in enumerate(zip(distances, durations)):
            legs.append(
                {
                    "segment_id": segment.segment_id,
                    "subleg_index": index,
                    "from_name": names[index],
                    "to_name": names[index + 1],
                    "distance_m": distance_m,
                    "duration_s": duration_s,
                }
            )
    return legs


def _minimum_day_boundaries(
    legs: Sequence[dict[str, object]],
) -> list[tuple[int, int]]:
    size = len(legs)
    best: list[tuple[int, int, int, int, int] | None] = [None] * (size + 1)
    previous: list[int | None] = [None] * (size + 1)
    best[0] = (0, 0, 0, 0, 0)
    for start in range(size):
        if best[start] is None:
            continue
        distance_m = 0
        duration_s = 0
        for end in range(start, size):
            distance_m += int(legs[end]["distance_m"])
            duration_s += int(legs[end]["duration_s"])
            if distance_m > 120_000 or duration_s > 21_600:
                break
            distance_miss = 0 if 80_000 <= distance_m else 1
            duration_miss = 0 if 14_400 <= duration_s else 1
            candidate = (
                best[start][0] + 1,
                best[start][1] + distance_miss,
                best[start][2] + duration_miss,
                best[start][3] + max(0, 80_000 - distance_m),
                best[start][4] + max(0, 14_400 - duration_s),
            )
            if best[end + 1] is None or candidate < best[end + 1]:
                best[end + 1] = candidate
                previous[end + 1] = start
    if previous[size] is None:
        raise ValueError("At least one API subleg exceeds the daily riding limit.")
    boundaries: list[tuple[int, int]] = []
    end = size
    while end:
        start = previous[end]
        if start is None:
            raise ValueError("Unable to build a continuous daily itinerary.")
        boundaries.append((start, end))
        end = start
    return list(reversed(boundaries))


def _proportional_durations(
    distances: Sequence[int], total_duration_s: int
) -> tuple[int, ...]:
    total_distance = sum(distances)
    if not distances or total_distance <= 0:
        return ()
    remaining = total_duration_s
    values: list[int] = []
    for index, distance in enumerate(distances):
        value = (
            remaining
            if index == len(distances) - 1
            else round(total_duration_s * distance / total_distance)
        )
        values.append(value)
        remaining -= value
    return tuple(values)


def build_review_markdown(
    segments: Sequence[PlannedSegment], *, profile: str = "coastal"
) -> str:
    """Render the route and its unresolved review work for a human reviewer."""
    main = tuple(segment for segment in segments if not _is_optional(segment))
    totals = _totals(main)
    days, _ = _day_summaries(main, profile)
    schedule = _schedule_contract(days, profile)
    distance_m = int(totals["distance_m"])
    unknown_m = int(totals["unknown_distance_m"])
    blank_name_m = sum(
        step.distance_m
        for segment in main
        for step in segment.selected.steps
        if not step.road_name.strip()
    )
    lines = [
        "# 路线人工复核",
        "",
        "> **临时路线：仍需道路级复核。** 自动分类/审核不等于现场或权威道路核验；不得据此宣称已完全避开国道、高速或货运道路。",
        "",
        f"- UNKNOWN：{unknown_m} m（{unknown_m * 100 / distance_m:.2f}%）；其中未命名道路 {blank_name_m} m。" if distance_m else "- UNKNOWN：0 m。",
        "- AMap 配额受限的补充探路清单见 `summary.json`；未完成的并行道路探测保持 provisional。",
        "- 国道本身不阻断发布；仅在距离接近且有更安全平行道路时切换，硬风险和货运风险仍阻断。",
        f"- {schedule['deadline_note']}",
        "",
    ]
    if schedule["deadline_feasible"]:
        lines.extend(
            [
                "## 每日计划",
                "",
                "| 天 | 起点 | 住宿/网络终点 | 距离 | 预计骑行时长 | 可行性 |",
                "| ---: | --- | --- | ---: | ---: | --- |",
                *(
                    f"| {day['day']} | {day['from_name']} | {day['to_name']} | {int(day['distance_m']) / 1000:.1f} km | {int(day['duration_s']) / 3600:.2f} h | "
                    f"{'≤6h' if day['duration_limit_met'] else '>6h'}；住宿/网络待确认 |"
                    for day in days
                ),
                "",
            ]
        )
    else:
        riding_day_excess = max(0, schedule["riding_day_count"] - int(schedule["max_riding_days"]))
        lines.extend(
            [
                "## 非执行排程诊断",
                "",
                f"- 需要{schedule['riding_day_count']}个骑行日；最多{schedule['max_riding_days']}个骑行日，超出{riding_day_excess}天。",
                "- 该路线不满足硬性排程约束，未渲染每日计划、住宿或网络安排。",
                "",
            ]
        )
    lines.extend(
        [
        "## 路段状态",
        "",
        "| 路段 | 起点 | 终点 | 距离 (m) | 时长 (s) | 复核状态 |",
        "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for segment in segments:
        lines.append(
            "| {segment_id} | {from_name} | {to_name} | {distance} | {duration} | {status} |".format(
                segment_id=segment.segment_id,
                from_name=segment.from_waypoint.name,
                to_name=segment.to_waypoint.name,
                distance=segment.selected.distance_m,
                duration=segment.selected.duration_s,
                status=_review_status_label(_review_status(segment)),
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


def _schedule_contract(
    days: Sequence[dict[str, object]], profile: str
) -> dict[str, object]:
    route_labels = {
        "coastal": "沿海安全优先路线",
        "inland": "内陆路线",
        "execution": "江西线执行路线",
    }
    try:
        route_label = route_labels[profile]
    except KeyError as error:
        raise ValueError(f"unsupported route profile: {profile}") from error

    available_days = (_DEADLINE_END - _DEADLINE_START).days + 1
    max_riding_days = _MAX_RIDING_DAYS_BY_PROFILE[profile]
    buffer_days = available_days - max_riding_days
    work_duration_s = _REQUIRED_WORK_HOURS_PER_DAY * 3_600
    riding_duration_s = _MAX_RIDING_HOURS_PER_DAY * 3_600
    combined_duration_s = work_duration_s + riding_duration_s
    # Day 0 is the Shanghai prelude; the 16-day cap counts only long-distance
    # riding days (Day 1 and beyond). Daily-time constraints still apply to
    # every published day so a city-prelude over the riding-time budget is
    # flagged separately.
    riding_days = [day for day in days if int(day.get("day", 0)) >= 1]
    riding_day_count = len(riding_days)
    daily_time_constraints_met = all(
        int(day["duration_s"]) <= riding_duration_s
        and int(day["duration_s"]) + work_duration_s <= combined_duration_s
        for day in days
    )
    deadline_feasible = (
        riding_day_count <= max_riding_days and daily_time_constraints_met
    )
    if deadline_feasible:
        deadline_note = (
            f"{route_label}可在8月13日至8月30日的{available_days}天自然日窗口内以"
            f"{riding_day_count}个骑行日完成（保留{buffer_days}天缓冲），"
            f"并保留每日{_REQUIRED_WORK_HOURS_PER_DAY}小时工作且每日骑行不超过"
            f"{_MAX_RIDING_HOURS_PER_DAY}小时。"
        )
    else:
        deadline_note = (
            f"{route_label}需{riding_day_count}个骑行日，超过最多{max_riding_days}个骑行日"
            f"的硬约束；8月13日至8月30日的{available_days}天自然日窗口仅保留"
            f"{buffer_days}天缓冲，"
            f"同时保留每日{_REQUIRED_WORK_HOURS_PER_DAY}小时工作且每日骑行不超过"
            f"{_MAX_RIDING_HOURS_PER_DAY}小时。"
        )
    return {
        "deadline_start": _DEADLINE_START.isoformat(),
        "deadline_end": _DEADLINE_END.isoformat(),
        "deadline_available_days": available_days,
        "max_riding_days": max_riding_days,
        "buffer_days": buffer_days,
        "riding_day_count": riding_day_count,
        "required_work_hours_per_day": _REQUIRED_WORK_HOURS_PER_DAY,
        "max_riding_hours_per_day": _MAX_RIDING_HOURS_PER_DAY,
        "daily_time_constraints_met": daily_time_constraints_met,
        "deadline_feasible": deadline_feasible,
        "deadline_note": deadline_note,
    }


def _review_status_label(status: str) -> str:
    return {
        "automatic_checks_passed": "自动检查通过（仍需道路级复核）",
        "review_required": "需人工复核",
        "unresolved": "未解析",
        "hard_review": "阻断：不得作为可骑行路线发布",
    }.get(status, "未标注")


def _position(point: Coordinate) -> list[float]:
    wgs84 = gcj02_to_wgs84(point)
    return [wgs84.lon, wgs84.lat]


def _step_properties(
    segment: PlannedSegment, step: RouteStep, days: Sequence[int]
) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "day": days[0] if days else None,
        "days": list(days),
        "from_name": segment.from_waypoint.name,
        "to_name": segment.to_waypoint.name,
        "road_name": step.road_name,
        "road_class": step.road_class.value,
        "distance_m": step.distance_m,
        "segment_duration_s": segment.selected.duration_s,
        "risk_tags": sorted(effective_risk_tags(step, segment.rule.verified_safe_steps)),
        "review_status": _review_status(segment),
        "reroute_status": segment.rule.reroute_status,
        "reroute_reason": segment.rule.reroute_reason,
        "optional_branch": _is_optional(segment),
        "branch_id": _branch_id(segment),
    }


def _is_optional(segment: PlannedSegment) -> bool:
    return not (
        segment.from_waypoint.include_in_main_totals
        and segment.to_waypoint.include_in_main_totals
    )


def _branch_id(segment: PlannedSegment) -> str:
    """Publish a stable branch enum without relying on display names in the web UI."""
    waypoint_branch_ids = {
        segment.from_waypoint.branch,
        segment.to_waypoint.branch,
    }
    if not _is_optional(segment):
        if waypoint_branch_ids != {"main"}:
            raise ValueError("Main route segments must use branch_id main")
        return "main"

    optional_ids = waypoint_branch_ids - {"main"}
    if len(optional_ids) != 1 or not optional_ids <= _BRANCH_IDS - {"main"}:
        raise ValueError("Optional route segments require branch_id ningbo or shenzhen")
    return optional_ids.pop()


def _review_status(segment: PlannedSegment) -> str:
    if any(not step.polyline_gcj for step in segment.selected.steps):
        return "unresolved"
    if any(
        effective_risk_tags(step, segment.rule.verified_safe_steps)
        & {"hard", "freight"}
        for step in segment.selected.steps
    ):
        return "hard_review"
    if _has_pending_review(segment):
        return "review_required"
    return "automatic_checks_passed"


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
        if _has_pending_review(segment)
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
        "tourism_distance_m": distances[RoadClass.TOURISM.value],
        "unknown_distance_m": distances[RoadClass.UNKNOWN.value],
        "city_distance_m": distances[RoadClass.CITY.value],
    }


def _has_pending_review(segment: PlannedSegment) -> bool:
    return (
        any(item.severity in {"warning", "hard"} for item in segment.reviews)
        or any(
            effective_risk_tags(step, segment.rule.verified_safe_steps)
            & {"hard", "freight"}
            for step in segment.selected.steps
        )
    )
