#!/usr/bin/env python3
"""Resolve main-route POIs while preserving all AMap candidates for review."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.amap import AmapClient, load_amap_key
from route_planner.config import load_route_config
from route_planner.coordinates import resolve_waypoints
from route_planner.models import ResolutionReport


def main() -> int:
    args = _arguments()
    config = load_route_config(args.config)
    client = AmapClient(load_amap_key(args.env), args.cache_dir)
    report = resolve_waypoints(config, client)
    _write_report(args.output, report)
    _print_review_table(report)
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="解析沿海主线 POI，并输出待复核候选项")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    return parser.parse_args()


def _write_report(path: Path, report: ResolutionReport) -> None:
    payload = _resolution_payload(report)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if isinstance(existing, dict):
            for key in ("checkin_resolutions", "unresolved_checkin_queries"):
                if isinstance(existing.get(key), list):
                    payload[key] = existing[key]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def _resolution_payload(report: ResolutionReport) -> dict[str, object]:
    return {
        "resolutions": [
            {
                "query": resolution.query,
                "city": resolution.city,
                "candidates": [
                    {
                        "poi_id": candidate.poi_id,
                        "name": candidate.name,
                        "formatted_address": candidate.formatted_address,
                        "district": candidate.district,
                        "location_gcj": {
                            "lon": candidate.location_gcj.lon,
                            "lat": candidate.location_gcj.lat,
                        },
                        "selected": candidate is resolution.selected,
                    }
                    for candidate in resolution.candidates
                ],
            }
            for resolution in report.resolutions
        ],
        "unresolved_queries": list(report.unresolved_queries),
    }


def _print_review_table(report: ResolutionReport) -> None:
    ambiguous = [resolution for resolution in report.resolutions if len(resolution.candidates) > 1]
    if not ambiguous:
        return
    print("以下 POI 有多个候选项，未自动选择，请人工复核：")
    print("| 查询 | 城市 | 候选名称 | 地址 | 区县 |")
    print("| --- | --- | --- | --- | --- |")
    for resolution in ambiguous:
        for candidate in resolution.candidates:
            print(
                f"| {resolution.query} | {resolution.city} | {candidate.name} | "
                f"{candidate.formatted_address} | {candidate.district} |"
            )


if __name__ == "__main__":
    raise SystemExit(main())
