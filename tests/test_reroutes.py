import json
from pathlib import Path
import tempfile
import unittest

from route_planner.models import (
    CandidateRoute,
    Coordinate,
    PlannedSegment,
    RoadClass,
    RouteStep,
    SegmentRule,
    Waypoint,
)
from route_planner.reroutes import compare_candidate, load_probe_definitions


def segment(
    *,
    segment_id="start-to-end",
    national_m=0,
    unknown_m=0,
    freight_m=0,
    hard_m=0,
    distance_m=80_000,
    baseline_m=80_000,
    subleg_distances_m=None,
):
    start = Waypoint(
        "start", "起点", "测试市", "起点", Coordinate(120.0, 30.0)
    )
    end = Waypoint(
        "end", "终点", "测试市", "终点", Coordinate(120.5, 30.5)
    )
    steps = []
    definitions = (
        (national_m, "沿G105骑行", "G105", RoadClass.NATIONAL, frozenset()),
        (unknown_m, "沿未分类道路骑行", "未分类道路", RoadClass.UNKNOWN, frozenset()),
        (freight_m, "沿物流大道骑行", "物流大道", RoadClass.CITY, frozenset({"freight"})),
        (hard_m, "沿快速路骑行", "城市快速路", RoadClass.CITY, frozenset({"hard"})),
    )
    for length, instruction, road_name, road_class, risk_tags in definitions:
        if length:
            steps.append(
                RouteStep(
                    instruction,
                    road_name,
                    length,
                    (start.coordinate, end.coordinate),
                    road_class,
                    risk_tags,
                )
            )
    classified_m = national_m + unknown_m + freight_m + hard_m
    if classified_m < distance_m:
        steps.append(
            RouteStep(
                "沿城市道路骑行",
                "城市道路",
                distance_m - classified_m,
                (start.coordinate, end.coordinate),
                RoadClass.CITY,
            )
        )
    selected = CandidateRoute(0, distance_m, 18_000, tuple(steps))
    sublegs = tuple(subleg_distances_m or (distance_m,))
    return PlannedSegment(
        segment_id,
        start,
        end,
        SegmentRule(segment_id),
        baseline_m,
        selected,
        distance_m / baseline_m,
        sublegs,
        subleg_durations_s=tuple(
            round(18_000 * value / distance_m) for value in sublegs
        ),
    )


class ProbeDefinitionTests(unittest.TestCase):
    def test_high_exposure_segments_have_second_pass_town_chains(self):
        payload = json.loads(
            Path("config/inland-reroute-probes.json").read_text(encoding="utf-8")
        )
        candidates = {
            item["segment_id"]: {
                candidate["candidate_id"] for candidate in item["candidates"]
            }
            for item in payload["probes"]
        }

        self.assertIn("s229-yihe-bypass", candidates["main-22-to-main-23"])
        self.assertIn("zengtian-county-bypass", candidates["main-22-to-main-23"])
        self.assertIn("xinjiang-south-bank-towns", candidates["main-11-to-main-12"])
        self.assertIn("yiyang-gexi-shortcut", candidates["main-11-to-main-12"])
        self.assertIn("egong-xiache-beidun", candidates["main-21-to-main-22"])
        self.assertIn("xiache-shortcut", candidates["main-21-to-main-22"])
        self.assertIn("zishan-huanglin-shadi", candidates["main-17-to-main-18"])

    def test_loads_evidence_and_named_anchor_sets_for_a_known_segment(self):
        payload = {
            "route_id": "inland-main",
            "probes": [
                {
                    "segment_id": "main-19-to-main-20",
                    "priority": "P0",
                    "evidence_urls": ["https://example.gov.cn/g105"],
                    "candidates": [
                        {
                            "candidate_id": "local-east",
                            "anchor_queries": ["信丰县小江镇", "龙南市里仁镇"],
                            "road_hint": "省道与城镇道路",
                        }
                    ],
                }
            ],
        }

        probes = self._load(payload, {"main-19-to-main-20"})

        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].priority, "P0")
        self.assertEqual(probes[0].evidence_urls, ("https://example.gov.cn/g105",))
        self.assertEqual(
            probes[0].candidates[0].anchor_queries,
            ("信丰县小江镇", "龙南市里仁镇"),
        )

    def test_rejects_unknown_segment_priority_and_duplicate_candidate_ids(self):
        base = {
            "route_id": "inland-main",
            "probes": [
                {
                    "segment_id": "unknown-segment",
                    "priority": "P9",
                    "evidence_urls": [],
                    "candidates": [
                        {"candidate_id": "same", "anchor_queries": ["甲镇"], "road_hint": "甲路"},
                        {"candidate_id": "same", "anchor_queries": ["乙镇"], "road_hint": "乙路"},
                    ],
                }
            ],
        }
        cases = (
            (base, {"known-segment"}, "unknown segment"),
            ({**base, "probes": [{**base["probes"][0], "segment_id": "known-segment"}]}, {"known-segment"}, "priority"),
            (
                {
                    **base,
                    "probes": [
                        {
                            **base["probes"][0],
                            "segment_id": "known-segment",
                            "priority": "P1",
                        }
                    ],
                },
                {"known-segment"},
                "duplicate candidate",
            ),
        )
        for payload, valid_ids, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self._load(payload, valid_ids)

    def test_requires_evidence_for_p0_and_nonempty_anchor_sets(self):
        base = {
            "route_id": "inland-main",
            "probes": [
                {
                    "segment_id": "known-segment",
                    "priority": "P0",
                    "evidence_urls": [],
                    "candidates": [
                        {"candidate_id": "candidate", "anchor_queries": ["甲镇"], "road_hint": "甲路"}
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "P0 evidence"):
            self._load(base, {"known-segment"})

        base["probes"][0]["evidence_urls"] = ["https://example.gov.cn/road"]
        base["probes"][0]["candidates"][0]["anchor_queries"] = []
        with self.assertRaisesRegex(ValueError, "anchor"):
            self._load(base, {"known-segment"})

    @staticmethod
    def _load(payload, valid_segment_ids):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probes.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return load_probe_definitions(path, valid_segment_ids)


class CandidateComparisonTests(unittest.TestCase):
    def test_rejects_hard_and_freight_exposure(self):
        for risk, proposed in (
            ("hard", segment(national_m=0, hard_m=500)),
            ("freight", segment(national_m=0, freight_m=500)),
        ):
            with self.subTest(risk=risk):
                result = compare_candidate(
                    segment(national_m=40_000),
                    proposed,
                    full_baseline_m=1_680_000,
                    other_selected_m=1_720_000,
                    max_detour_ratio=1.15,
                )
                self.assertEqual(result.decision, "rejected")
                self.assertIn(risk, result.reasons)

    def test_rejects_a_route_wide_detour_over_fifteen_percent(self):
        result = compare_candidate(
            segment(national_m=40_000),
            segment(
                national_m=0,
                distance_m=220_000,
                baseline_m=80_000,
                subleg_distances_m=(55_000, 55_000, 55_000, 55_000),
            ),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )

        self.assertEqual(result.decision, "rejected")
        self.assertIn("route_detour_over_15_percent", result.reasons)

    def test_rejects_candidate_with_a_subleg_over_eighty_kilometres(self):
        result = compare_candidate(
            segment(national_m=40_000),
            segment(national_m=0, distance_m=100_000),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )

        self.assertEqual(result.decision, "rejected")
        self.assertIn("subleg_over_80_km", result.reasons)

    def test_accepts_a_large_national_reduction_within_route_budget(self):
        result = compare_candidate(
            segment(national_m=40_000, distance_m=90_000),
            segment(
                national_m=4_000,
                distance_m=105_000,
                subleg_distances_m=(52_000, 53_000),
            ),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )

        self.assertEqual(result.decision, "candidate")
        self.assertEqual(result.national_reduction_m, 36_000)
        self.assertEqual(result.distance_delta_m, 15_000)

    def test_marks_large_unknown_substitution_for_manual_review(self):
        result = compare_candidate(
            segment(national_m=30_000, unknown_m=1_000),
            segment(
                national_m=2_000,
                unknown_m=20_000,
                distance_m=90_000,
                subleg_distances_m=(45_000, 45_000),
            ),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )

        self.assertEqual(result.decision, "manual_review")
        self.assertIn("unknown_increase", result.reasons)

    def test_rejects_a_candidate_that_does_not_reduce_national_distance(self):
        result = compare_candidate(
            segment(national_m=20_000),
            segment(national_m=20_000),
            full_baseline_m=1_680_000,
            other_selected_m=1_720_000,
            max_detour_ratio=1.15,
        )

        self.assertEqual(result.decision, "rejected")
        self.assertIn("national_not_reduced", result.reasons)


if __name__ == "__main__":
    unittest.main()
