#!/usr/bin/env python3
"""Plan a resolved coastal route and atomically publish auditable artifacts."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.amap import AmapClient, load_amap_key
from route_planner.config import load_route_config
from route_planner.export import build_geojson, build_review_markdown, build_summary
from route_planner.manifest import build_manifest
from route_planner.models import Coordinate, PlannedSegment, RouteConfig, Waypoint
from route_planner.planner import RoutePlanner


def write_artifacts(
    output_dir: Path,
    geojson: dict[str, object],
    summary: dict[str, object],
    review_markdown: str,
    manifest: dict[str, object] | None = None,
) -> None:
    """Validate all JSON before atomically replacing the complete artifact set."""
    rendered = {
        "coastal-route.geojson": _validated_json(geojson),
        "summary.json": _validated_json(summary),
        "review.md": review_markdown,
    }
    if manifest is not None:
        rendered["route-manifest.json"] = _validated_json(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: set[Path] = set()
    try:
        for name, content in rendered.items():
            target = output_dir / name
            temporary = output_dir / f"{name}.tmp"
            temporary.write_text(content, encoding="utf-8")
            staged[target] = temporary
        for target, temporary in staged.items():
            if target.exists():
                backup = output_dir / f".{target.name}.{uuid4().hex}.bak"
                target.replace(backup)
                backups[target] = backup
            temporary.replace(target)
            published.add(target)
    except Exception:
        for target in published:
            target.unlink(missing_ok=True)
        for target, backup in backups.items():
            backup.replace(target)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def generate_from_segments(
    config: RouteConfig, segments: tuple[PlannedSegment, ...], output_dir: Path
) -> None:
    """Publish exactly the supplied immutable plans and their lossless audit manifest."""
    write_artifacts(
        output_dir,
        build_geojson(segments),
        build_summary(segments, config.max_detour_ratio),
        build_review_markdown(segments),
        build_manifest(config.route_id, segments),
    )


def load_resolved_config(config_path: Path, resolutions_path: Path) -> RouteConfig:
    """Attach manually selected GCJ-02 POI results to the immutable route config."""
    config = load_route_config(config_path)
    try:
        resolution_data = json.loads(resolutions_path.read_text(encoding="utf-8"))
        if not isinstance(resolution_data, dict) or resolution_data.get("unresolved_queries"):
            raise ValueError
        selected = {
            (_string(item, "query"), _string(item, "city")): _selected_coordinate(item)
            for item in _list(resolution_data.get("resolutions"), "resolutions")
        }
        waypoints = tuple(_resolved_waypoint(waypoint, selected) for waypoint in config.waypoints)
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("Resolved POI input is incomplete or invalid.") from error
    return replace(config, waypoints=waypoints)


def plan_live_segments(
    config: RouteConfig, env_path: Path, cache_dir: Path, requested_segments: tuple[str, ...]
) -> tuple[PlannedSegment, ...]:
    """Use existing AMap and planner components to construct live planned segments."""
    planner = RoutePlanner(AmapClient(load_amap_key(env_path), cache_dir))
    requested = set(requested_segments)
    available = {
        f"{start.id}-to-{end.id}": (start, end)
        for start, end in zip(config.waypoints, config.waypoints[1:])
    }
    if requested - available.keys():
        raise ValueError("Requested segment is not in the resolved main route.")
    selected_ids = tuple(requested_segments) if requested_segments else tuple(available)
    try:
        return tuple(
            planner.plan_segment(start, end, config.segment_rules[segment_id])
            for segment_id in selected_ids
            for start, end in (available[segment_id],)
        )
    except KeyError as error:
        raise ValueError("A selected route segment has no configured rule.") from error


def _validated_json(value: dict[str, object]) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    json.loads(rendered)
    return rendered


def _selected_coordinate(value: object) -> Coordinate:
    if not isinstance(value, dict):
        raise ValueError
    candidates = _list(value.get("candidates"), "candidates")
    selected = [candidate for candidate in candidates if isinstance(candidate, dict) and candidate.get("selected") is True]
    if len(selected) != 1:
        raise ValueError
    location = selected[0].get("location_gcj")
    if not isinstance(location, dict):
        raise ValueError
    lon, lat = location.get("lon"), location.get("lat")
    if not _number(lon) or not _number(lat):
        raise ValueError
    return Coordinate(float(lon), float(lat))


def _resolved_waypoint(
    waypoint: Waypoint, selected: dict[tuple[str, str], Coordinate]
) -> Waypoint:
    try:
        return replace(waypoint, coordinate=selected[(waypoint.query, waypoint.city)])
    except KeyError as error:
        raise ValueError("Every main waypoint needs one selected POI resolution.") from error


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, dict) or not isinstance(value.get(label), str) or not value[label]:
        raise ValueError(f"{label} must be a non-empty string")
    return value[label]


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--segment", action="append", default=[], help="segment id to generate; repeatable")
    args = parser.parse_args(argv)
    try:
        config = load_resolved_config(args.config, args.resolutions)
        segments = plan_live_segments(config, args.env, args.cache_dir, tuple(args.segment))
        generate_from_segments(config, segments, args.output_dir)
    except Exception:
        print("ERROR: route generation failed", file=sys.stderr)
        return 1
    print(f"Wrote route artifacts to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
