#!/usr/bin/env python3
"""Plan a resolved route profile and atomically publish auditable artifacts."""

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
from route_planner.artifacts import ArtifactPaths
from route_planner.config import load_route_config
from route_planner.export import build_geojson, build_review_markdown, build_summary
from route_planner.manifest import build_manifest, load_manifest
from route_planner.models import Coordinate, PlannedSegment, RouteConfig, Waypoint
from route_planner.planner import RoutePlanner


QUOTA_LIMITED_PROBES = (
    "main-06-to-main-07",
    "main-07-to-main-08",
    "main-09-to-main-10",
    "main-10-to-main-11",
    "main-11-to-main-12",
    "main-17-to-main-18",
)


def write_artifacts(
    output_dir: Path,
    geojson: dict[str, object],
    summary: dict[str, object],
    review_markdown: str,
    manifest: dict[str, object] | None = None,
    *,
    profile: str = "coastal",
) -> None:
    """Validate all JSON before atomically replacing the complete artifact set."""
    paths = ArtifactPaths.for_profile(output_dir, profile)
    rendered = {
        paths.geojson: _validated_json(geojson),
        paths.summary: _validated_json(summary),
        paths.review: review_markdown,
    }
    if manifest is not None:
        rendered[paths.manifest] = _validated_json(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: set[Path] = set()
    try:
        for target, content in rendered.items():
            temporary = output_dir / f"{target.name}.tmp"
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
    config: RouteConfig,
    segments: tuple[PlannedSegment, ...],
    output_dir: Path,
    *,
    profile: str = "coastal",
) -> None:
    """Publish exactly the supplied immutable plans and their lossless audit manifest."""
    write_artifacts(
        output_dir,
        build_geojson(segments, profile=profile),
        build_summary(
            segments,
            config.max_detour_ratio,
            quota_limited_probes=QUOTA_LIMITED_PROBES,
            profile=profile,
        ),
        build_review_markdown(segments, profile=profile),
        build_manifest(config.route_id, segments),
        profile=profile,
    )


def merge_refreshed_segments(
    config: RouteConfig,
    refreshed: tuple[PlannedSegment, ...],
    output_dir: Path,
    *,
    profile: str = "coastal",
) -> tuple[PlannedSegment, ...]:
    """Merge selected refreshes into a complete, config-aligned published manifest."""
    paths = ArtifactPaths.for_profile(output_dir, profile)
    existing = load_manifest(paths.manifest, config.route_id)
    expected = tuple(
        f"{start.id}-to-{end.id}"
        for start, end in zip(config.waypoints, config.waypoints[1:])
    )
    if tuple(segment.segment_id for segment in existing) != expected:
        raise ValueError("Selective refresh requires a complete ordered route manifest.")
    replacements = {segment.segment_id: segment for segment in refreshed}
    if len(replacements) != len(refreshed) or not replacements.keys() <= set(expected):
        raise ValueError("Selective refresh contains duplicate or unknown segments.")
    for segment, start, end in zip(existing, config.waypoints, config.waypoints[1:]):
        rule = config.segment_rules.get(segment.segment_id)
        if (
            rule is None
            or segment.rule != rule
            or segment.from_waypoint.id != start.id
            or segment.to_waypoint.id != end.id
        ):
            raise ValueError("Selective refresh requires a config-aligned manifest.")
    return tuple(replacements.get(segment.segment_id, segment) for segment in existing)


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
    parser.add_argument("--profile", choices=("coastal", "inland", "execution"), required=True)
    args = parser.parse_args(argv)
    try:
        config = load_resolved_config(args.config, args.resolutions)
        segments = plan_live_segments(config, args.env, args.cache_dir, tuple(args.segment))
        if args.segment:
            segments = merge_refreshed_segments(
                config, segments, args.output_dir, profile=args.profile
            )
        generate_from_segments(config, segments, args.output_dir, profile=args.profile)
    except Exception:
        print("ERROR: route generation failed", file=sys.stderr)
        return 1
    print(f"Wrote route artifacts to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
