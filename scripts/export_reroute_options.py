#!/usr/bin/env python3
"""Export material safety detours as optional map overlays."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from route_planner.amap import AmapClient, load_amap_key
from route_planner.manifest import load_manifest
from route_planner.planner import RoutePlanner
from route_planner.reroute_options import RerouteOption, build_reroute_options
from route_planner.reroutes import load_probe_definitions
from scripts.generate_route import load_resolved_config


def select_map_option_results(
    report: dict[str, object], *, min_national_reduction_m: int = 10_000
) -> list[dict[str, object]]:
    """Keep reviewable candidates that remove a material amount of national road."""
    results = report.get("results")
    if not isinstance(results, list):
        raise ValueError("Reroute report requires a results list")
    selected: list[dict[str, object]] = []
    for value in results:
        if not isinstance(value, dict):
            raise ValueError("Reroute report results must be objects")
        reduction = value.get("national_reduction_m")
        distance_delta = value.get("distance_delta_m")
        efficient_small_detour = (
            isinstance(reduction, int)
            and isinstance(distance_delta, int)
            and reduction >= 3_000
            and 0 <= distance_delta <= reduction
        )
        if (
            value.get("decision") in {"candidate", "manual_review"}
            and isinstance(reduction, int)
            and (reduction >= min_national_reduction_m or efficient_small_detour)
        ):
            selected.append(dict(value))
    return [
        candidate
        for candidate in selected
        if not any(
            _dominates(other, candidate)
            for other in selected
            if other is not candidate
        )
    ]


def _dominates(
    challenger: dict[str, object], candidate: dict[str, object]
) -> bool:
    if challenger.get("segment_id") != candidate.get("segment_id"):
        return False
    challenger_reduction = challenger.get("national_reduction_m")
    candidate_reduction = candidate.get("national_reduction_m")
    challenger_delta = challenger.get("distance_delta_m")
    candidate_delta = candidate.get("distance_delta_m")
    if not all(
        isinstance(value, int)
        for value in (
            challenger_reduction,
            candidate_reduction,
            challenger_delta,
            candidate_delta,
        )
    ):
        return False
    return (
        challenger_reduction >= candidate_reduction
        and challenger_delta <= candidate_delta
        and (
            challenger_reduction > candidate_reduction
            or challenger_delta < candidate_delta
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-national-reduction-m", type=int, default=10_000)
    args = parser.parse_args(argv)

    try:
        config = load_resolved_config(args.config, args.resolutions)
        published = load_manifest(args.manifest, config.route_id)
        current_by_id = {item.segment_id: item for item in published}
        definitions = load_probe_definitions(args.probes, set(current_by_id))
        definition_by_id = {item.segment_id: item for item in definitions}
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("route_id") != config.route_id:
            raise ValueError("Reroute report does not match the route")
        results = select_map_option_results(
            report,
            min_national_reduction_m=args.min_national_reduction_m,
        )
        planner = RoutePlanner(AmapClient(load_amap_key(args.env), args.cache_dir))
        options: list[RerouteOption] = []
        for result in results:
            segment_id = _required_string(result, "segment_id")
            candidate_id = _required_string(result, "candidate_id")
            definition = definition_by_id[segment_id]
            candidate = next(
                item for item in definition.candidates if item.candidate_id == candidate_id
            )
            current = current_by_id[segment_id]
            proposed = planner.plan_segment(
                current.from_waypoint,
                current.to_waypoint,
                replace(
                    current.rule,
                    anchor_queries=candidate.anchor_queries,
                    parallel_road_available=False,
                    allowed_national_m=0,
                    national_exception_reason="",
                ),
            )
            options.append(
                RerouteOption(
                    candidate_id=candidate_id,
                    label="避国道绕行线",
                    current=current,
                    proposed=proposed,
                    decision=_required_string(result, "decision"),
                )
            )
        _write_json(args.output, build_reroute_options(options))
    except Exception as error:
        print(f"ERROR: reroute option export stopped: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {len(options)} reroute options to {args.output}")
    return 0


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Reroute result requires {key}")
    return item


def _write_json(path: Path, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    json.loads(rendered)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
