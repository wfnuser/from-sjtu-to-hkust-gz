#!/usr/bin/env python3
"""Resolve a route configuration's main POIs while preserving AMap provenance."""

from __future__ import annotations

import argparse
from copy import deepcopy
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
    parser = argparse.ArgumentParser(description="解析主线 POI，并输出待复核候选项")
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
            _preserve_manual_selections(payload, existing)
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


def _preserve_manual_selections(
    payload: dict[str, object], existing: dict[str, object]
) -> None:
    approved = _approved_manual_candidates(existing)
    resolutions = payload["resolutions"]
    assert isinstance(resolutions, list)
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            continue
        key = (resolution.get("query"), resolution.get("city"))
        previous = approved.get(key)
        if previous is None:
            continue
        selection, selected_candidate = previous
        candidates = resolution.get("candidates")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate["selected"] = False
        matching = [
            candidate
            for candidate in candidates
            if isinstance(candidate, dict)
            and candidate.get("poi_id") == selection["selected_poi_id"]
        ]
        if len(matching) == 1:
            matching[0]["selected"] = True
        else:
            candidates.append(deepcopy(selected_candidate))
        resolution["selection"] = deepcopy(selection)
    payload["unresolved_queries"] = [
        resolution["query"]
        for resolution in resolutions
        if isinstance(resolution, dict)
        and not any(
            isinstance(candidate, dict) and candidate.get("selected") is True
            for candidate in resolution.get("candidates", [])
        )
    ]


def _approved_manual_candidates(
    existing: dict[str, object],
) -> dict[tuple[object, object], tuple[dict[str, object], dict[str, object]]]:
    result: dict[tuple[object, object], tuple[dict[str, object], dict[str, object]]] = {}
    resolutions = existing.get("resolutions")
    if not isinstance(resolutions, list):
        return result
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            continue
        selection = resolution.get("selection")
        candidates = resolution.get("candidates")
        if (
            not isinstance(selection, dict)
            or selection.get("mode") != "manual"
            or not isinstance(selection.get("selected_poi_id"), str)
            or not selection["selected_poi_id"]
            or not isinstance(candidates, list)
        ):
            continue
        selected = [
            candidate
            for candidate in candidates
            if isinstance(candidate, dict)
            and candidate.get("selected") is True
            and candidate.get("poi_id") == selection["selected_poi_id"]
        ]
        if len(selected) == 1:
            result[(resolution.get("query"), resolution.get("city"))] = (selection, selected[0])
    return result


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
