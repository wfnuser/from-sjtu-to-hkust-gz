#!/usr/bin/env python3
"""Generate deterministic placeholder route artifacts; live planning belongs to Task 7."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.export import build_geojson, build_review_markdown, build_summary
from route_planner.models import (
    CandidateRoute,
    Coordinate,
    PlannedSegment,
    RoadClass,
    RouteStep,
    SegmentRule,
    Waypoint,
)


def deterministic_segments() -> tuple[PlannedSegment, ...]:
    """Return a no-network fixture used until Task 7 wires live AMap planning."""
    segment_id = "fixture-start-to-end"
    start = Waypoint("fixture-start", "示例起点", "上海", "示例起点", Coordinate(121.0, 31.0))
    end = Waypoint("fixture-end", "示例终点", "上海", "示例终点", Coordinate(121.02, 31.02))
    step = RouteStep(
        "沿示例县道骑行", "X101县道", 2_000,
        (Coordinate(121.0, 31.0), Coordinate(121.02, 31.02)), RoadClass.COUNTY,
    )
    return (
        PlannedSegment(
            segment_id, start, end, SegmentRule(segment_id, day=1), 1_800,
            CandidateRoute(0, 2_000, 600, (step,)), 2_000 / 1_800, (2_000,),
        ),
    )


def write_artifacts(
    output_dir: Path,
    geojson: dict[str, object],
    summary: dict[str, object],
    review_markdown: str,
) -> None:
    """Validate all JSON before atomically replacing the complete artifact set."""
    rendered = {
        "route.geojson": _validated_json(geojson),
        "summary.json": _validated_json(summary),
        "review.md": review_markdown,
    }
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


def _validated_json(value: dict[str, object]) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    json.loads(rendered)
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "web" / "data",
        help="directory for route.geojson, summary.json, and review.md",
    )
    parser.add_argument("--max-detour-ratio", type=float, default=1.15)
    args = parser.parse_args(argv)
    segments = deterministic_segments()
    write_artifacts(
        args.output_dir,
        build_geojson(segments),
        build_summary(segments, args.max_detour_ratio),
        build_review_markdown(segments),
    )
    print(f"Wrote deterministic fixture artifacts to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
