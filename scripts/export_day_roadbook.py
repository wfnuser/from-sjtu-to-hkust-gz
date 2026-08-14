#!/usr/bin/env python3
"""Export one published itinerary day as universal GPX 1.1 and Markdown."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any
import xml.etree.ElementTree as ET


GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", GPX_NS)
ET.register_namespace("xsi", XSI_NS)


def export_day(
    geojson: dict[str, Any],
    itinerary: dict[str, Any],
    day_number: int,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write one day's WGS84 track, route points, and compact roadbook."""
    day = next(
        (item for item in itinerary.get("days", []) if item.get("day") == day_number),
        None,
    )
    if not isinstance(day, dict) or not day.get("segments"):
        raise ValueError(f"Day {day_number} has no published riding segments.")

    features_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in geojson.get("features", []):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        segment_id = properties.get("segment_id")
        if isinstance(segment_id, str):
            features_by_segment[segment_id].append(feature)

    segments = []
    for segment_id in day["segments"]:
        features = features_by_segment.get(segment_id, [])
        if not features:
            raise ValueError(f"Missing published geometry for {segment_id}.")
        segments.append(_segment_record(segment_id, features))

    route_name = f"Day {day_number} {day['from_name']}至{day['to_name']}"
    waypoints = [(segments[0]["from_name"], segments[0]["coordinates"][0])]
    waypoints.extend((segment["to_name"], segment["coordinates"][-1]) for segment in segments)
    track = _deduplicate(
        point for segment in segments for point in segment["coordinates"]
    )
    if not track or waypoints[-1][1] != track[-1]:
        raise ValueError("Published day geometry does not end at the final waypoint.")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        "day-01-shanghai-to-tongxiang"
        if day_number == 1
        else f"day-{day_number:02d}-route"
    )
    gpx_path = output_dir / f"{stem}.gpx"
    markdown_path = output_dir / f"day-{day_number:02d}-roadbook.md"
    gpx_path.write_text(_build_gpx(route_name, waypoints, track), encoding="utf-8")
    markdown_path.write_text(
        _build_markdown(route_name, day, segments), encoding="utf-8"
    )
    return gpx_path, markdown_path


def _segment_record(segment_id: str, features: list[dict[str, Any]]) -> dict[str, Any]:
    first = features[0].get("properties") or {}
    last = features[-1].get("properties") or {}
    coordinates = _deduplicate(
        point
        for feature in features
        for point in _line_coordinates(feature)
    )
    road_distances: dict[str, int] = defaultdict(int)
    for feature in features:
        properties = feature.get("properties") or {}
        road_name = str(properties.get("road_name") or "未命名道路")
        road_distances[road_name] += int(properties.get("distance_m") or 0)
    roads = [
        name
        for name, _distance in sorted(
            road_distances.items(), key=lambda item: (-item[1], item[0])
        )[:8]
    ]
    return {
        "segment_id": segment_id,
        "from_name": str(first.get("from_name") or "起点"),
        "to_name": str(last.get("to_name") or "终点"),
        "distance_m": sum(
            int((feature.get("properties") or {}).get("distance_m") or 0)
            for feature in features
        ),
        "duration_s": int(first.get("segment_duration_s") or 0),
        "coordinates": coordinates,
        "roads": roads,
    }


def _line_coordinates(feature: dict[str, Any]) -> list[tuple[float, float]]:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if geometry.get("type") != "LineString" or not isinstance(coordinates, list):
        return []
    return [
        (float(point[0]), float(point[1]))
        for point in coordinates
        if isinstance(point, list) and len(point) >= 2
    ]


def _deduplicate(points) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result


def _build_gpx(
    route_name: str,
    waypoints: list[tuple[str, tuple[float, float]]],
    track: list[tuple[float, float]],
) -> str:
    root = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {
            "version": "1.1",
            "creator": "from-sjtu-to-hkust-gz",
            f"{{{XSI_NS}}}schemaLocation": (
                "http://www.topografix.com/GPX/1/1 "
                "http://www.topografix.com/GPX/1/1/gpx.xsd"
            ),
        },
    )
    metadata = ET.SubElement(root, f"{{{GPX_NS}}}metadata")
    ET.SubElement(metadata, f"{{{GPX_NS}}}name").text = route_name
    for name, (lon, lat) in waypoints:
        waypoint = ET.SubElement(
            root, f"{{{GPX_NS}}}wpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"}
        )
        ET.SubElement(waypoint, f"{{{GPX_NS}}}name").text = name

    route = ET.SubElement(root, f"{{{GPX_NS}}}rte")
    ET.SubElement(route, f"{{{GPX_NS}}}name").text = route_name
    for name, (lon, lat) in waypoints:
        point = ET.SubElement(
            route, f"{{{GPX_NS}}}rtept", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"}
        )
        ET.SubElement(point, f"{{{GPX_NS}}}name").text = name

    track_element = ET.SubElement(root, f"{{{GPX_NS}}}trk")
    ET.SubElement(track_element, f"{{{GPX_NS}}}name").text = route_name
    track_segment = ET.SubElement(track_element, f"{{{GPX_NS}}}trkseg")
    for lon, lat in track:
        ET.SubElement(
            track_segment,
            f"{{{GPX_NS}}}trkpt",
            {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"},
        )
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def _build_markdown(
    route_name: str, day: dict[str, Any], segments: list[dict[str, Any]]
) -> str:
    total_distance_m = int(day.get("distance_m") or 0)
    total_duration_s = int(day.get("duration_s") or 0)
    lines = [
        f"# {route_name}",
        "",
        f"> {day['from_name']} → {day['to_name']}",
        "",
        f"- 总里程：{total_distance_m / 1000:.1f} km",
        f"- 高德预计纯骑行时间：{_duration(total_duration_s)}",
        "- 轨迹坐标：WGS-84；时间不含停留、补给与现场绕行。",
        "",
        "| # | 分段 | 本段 | 累计 | 预计骑行 | 主要道路 |",
        "|---:|---|---:|---:|---:|---|",
    ]
    cumulative_m = 0
    for index, segment in enumerate(segments, 1):
        cumulative_m += segment["distance_m"]
        lines.append(
            "| {index} | {start} → {end} | {distance:.1f} km | {cumulative:.1f} km | {duration} | {roads} |".format(
                index=index,
                start=segment["from_name"],
                end=segment["to_name"],
                distance=segment["distance_m"] / 1000,
                cumulative=cumulative_m / 1000,
                duration=_duration(segment["duration_s"]),
                roads="、".join(segment["roads"]),
            )
        )
    lines.extend(
        [
            "",
            "## 使用提醒",
            "",
            "- GPX 同时包含路线点与完整轨迹，适合导入常见码表；活动记录仍按实际骑行独立生成。",
            "- 叶新公路为计划主通道，现场以非机动车通行标志、施工和车流为准。",
            "- 自动检查不等于道路级核验，出发前仍需查看天气、施工和禁行变化。",
            "",
        ]
    )
    return "\n".join(lines)


def _duration(seconds: int) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes = round(remainder / 60)
    return f"{hours} 小时 {minutes} 分" if hours else f"{minutes} 分"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geojson", type=Path, required=True)
    parser.add_argument("--itinerary", type=Path, required=True)
    parser.add_argument("--day", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    geojson = json.loads(args.geojson.read_text(encoding="utf-8"))
    itinerary = json.loads(args.itinerary.read_text(encoding="utf-8"))
    gpx_path, markdown_path = export_day(
        geojson, itinerary, args.day, args.output_dir
    )
    print(gpx_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
