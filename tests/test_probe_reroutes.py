import json
from pathlib import Path
import tempfile
import unittest

from route_planner.reroutes import ProbeCandidate, ProbeDefinition
from scripts.probe_reroutes import (
    evaluate_proposed_candidate,
    merge_result,
    ordered_probes,
    write_report,
)
from tests.test_reroutes import segment


def probe(segment_id, priority, candidate_id=None):
    return ProbeDefinition(
        segment_id=segment_id,
        priority=priority,
        evidence_urls=("https://example.gov.cn/road",),
        candidates=(
            ProbeCandidate(
                candidate_id or f"candidate-{segment_id}",
                ("测试镇",),
                "测试道路",
            ),
        ),
        scenic=priority == "SCENIC",
    )


class ProbeOrderingTests(unittest.TestCase):
    def test_orders_requested_priority_by_current_national_distance_descending(self):
        definitions = (
            probe("short-national", "P0"),
            probe("scenic", "SCENIC"),
            probe("long-national", "P0"),
        )
        current = {
            "short-national": segment(segment_id="short-national", national_m=20_000),
            "scenic": segment(segment_id="scenic", national_m=0),
            "long-national": segment(segment_id="long-national", national_m=40_000),
        }

        result = ordered_probes(definitions, current, "P0")

        self.assertEqual(
            [item.segment_id for item in result],
            ["long-national", "short-national"],
        )

    def test_rejects_priority_without_probe_definitions(self):
        with self.assertRaisesRegex(ValueError, "No P1 probes"):
            ordered_probes((probe("p0", "P0"),), {"p0": segment()}, "P1")


class ProposedCandidateReportTests(unittest.TestCase):
    def test_uses_all_other_published_segments_for_route_wide_budget(self):
        definition = probe("target", "P0")
        current = segment(
            segment_id="target", distance_m=80_000, baseline_m=80_000, national_m=30_000
        )
        proposed = segment(
            segment_id="target", distance_m=90_000, baseline_m=80_000, national_m=0
        )
        other = segment(
            segment_id="other", distance_m=1_600_000, baseline_m=1_600_000
        )

        report = evaluate_proposed_candidate(
            definition,
            definition.candidates[0],
            current,
            proposed,
            (current, other),
            1.15,
        )

        self.assertEqual(report["decision"], "candidate")
        self.assertAlmostEqual(report["projected_route_detour_ratio"], 1.69 / 1.68)
        self.assertEqual(report["national_reduction_m"], 30_000)

    def test_reports_before_after_metrics_anchor_queries_and_named_roads(self):
        definition = probe("target", "P0", "safe-road")
        current = segment(segment_id="target", national_m=20_000)
        proposed = segment(
            segment_id="target", national_m=1_000, unknown_m=4_000
        )

        report = evaluate_proposed_candidate(
            definition,
            definition.candidates[0],
            current,
            proposed,
            (current,),
            1.15,
        )

        self.assertEqual(report["candidate_id"], "safe-road")
        self.assertEqual(report["proposed"]["anchor_queries"], ["测试镇"])
        self.assertEqual(report["current"]["national_m"], 20_000)
        self.assertEqual(report["proposed"]["unknown_m"], 4_000)
        self.assertIn("G105", report["current"]["road_names"])
        self.assertIn("城市道路", report["proposed"]["road_names"])


class DurableReportTests(unittest.TestCase):
    def test_merging_same_probe_replaces_result_without_duplicates(self):
        first = {"segment_id": "target", "candidate_id": "safe-road", "decision": "candidate"}
        revised = {"segment_id": "target", "candidate_id": "safe-road", "decision": "manual_review"}
        report = {"schema_version": 1, "route_id": "inland-main", "results": []}

        report = merge_result(report, first)
        report = merge_result(report, revised)

        self.assertEqual(report["results"], [revised])

    def test_write_report_creates_valid_json_and_no_temporary_file(self):
        report = {
            "schema_version": 1,
            "route_id": "inland-main",
            "results": [
                {"segment_id": "target", "candidate_id": "safe-road", "decision": "candidate"}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reports" / "reroutes.json"

            write_report(path, report)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
