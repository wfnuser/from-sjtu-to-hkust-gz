import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from route_planner.manifest import load_manifest
from route_planner.roads import candidate_metrics
from scripts.generate_route import load_resolved_config


class InlandRerouteDecisionTests(unittest.TestCase):
    def setUp(self):
        self.probes = json.loads(
            Path("config/inland-reroute-probes.json").read_text(encoding="utf-8")
        )["probes"]
        self.report = json.loads(
            Path("cache/reports/inland-reroute-probes.json").read_text(encoding="utf-8")
        )["results"]
    def _load_decisions(self):
        decisions_path = Path("web/data/inland-reroute-decisions.json")
        self.assertTrue(decisions_path.exists(), "reviewed reroute decisions are not published")
        return json.loads(decisions_path.read_text(encoding="utf-8"))

    def test_every_priority_segment_has_one_metric_aligned_reviewed_decision(self):
        required = {
            item["segment_id"]
            for item in self.probes
            if item["priority"] in {"P0", "P1"}
        }
        decisions = {
            item["segment_id"]: item for item in self._load_decisions()["decisions"]
        }
        self.assertEqual(set(decisions), required)

        probe_candidates = {
            item["segment_id"]: {
                candidate["candidate_id"] for candidate in item["candidates"]
            }
            for item in self.probes
        }
        report = {
            (item["segment_id"], item["candidate_id"]): item
            for item in self.report
        }
        for segment_id, decision in decisions.items():
            self.assertIn(decision["status"], {"adopted", "rejected", "manual_review"})
            self.assertTrue(decision["decision_reason"].strip())
            candidate_id = decision["selected_candidate_id"]
            self.assertIn(candidate_id, probe_candidates[segment_id])
            measured = report[(segment_id, candidate_id)]
            self.assertEqual(decision["current"], measured["current"])
            self.assertEqual(decision["proposed"], measured["proposed"])
            self.assertEqual(
                decision["national_reduction_m"], measured["national_reduction_m"]
            )
            self.assertEqual(decision["distance_delta_m"], measured["distance_delta_m"])

    def test_remaining_national_segments_match_published_route_in_descending_order(self):
        config = load_resolved_config(
            Path("config/inland-route.json"),
            Path("config/inland-poi-resolutions.json"),
        )
        segments = load_manifest(
            Path("web/data/inland-route-manifest.json"), config.route_id
        )
        expected = [
            {
                "segment_id": segment.segment_id,
                "from_name": segment.from_waypoint.name,
                "to_name": segment.to_waypoint.name,
                "national_m": candidate_metrics(segment.selected).national_m,
            }
            for segment in sorted(
                segments,
                key=lambda item: -candidate_metrics(item.selected).national_m,
            )
            if candidate_metrics(segment.selected).national_m
        ]

        self.assertEqual(self._load_decisions()["remaining_national_segments"], expected)

    def test_reviewed_status_and_reason_are_visible_in_the_route_config(self):
        config = load_resolved_config(
            Path("config/inland-route.json"),
            Path("config/inland-poi-resolutions.json"),
        )

        for decision in self._load_decisions()["decisions"]:
            rule = config.segment_rules[decision["segment_id"]]
            self.assertEqual(rule.reroute_status, decision["status"])
            self.assertEqual(rule.reroute_reason, decision["decision_reason"])

    def test_exporter_rebuilds_the_published_decisions_from_reviewed_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "decisions.json"
            result = subprocess.run(
                [
                    "python3",
                    "scripts/export_reroute_decisions.py",
                    "--config",
                    "config/inland-route.json",
                    "--resolutions",
                    "config/inland-poi-resolutions.json",
                    "--manifest",
                    "web/data/inland-route-manifest.json",
                    "--probes",
                    "config/inland-reroute-probes.json",
                    "--report",
                    "cache/reports/inland-reroute-probes.json",
                    "--reviews",
                    "config/inland-reroute-reviews.json",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            rebuilt = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(rebuilt, self._load_decisions())


if __name__ == "__main__":
    unittest.main()
