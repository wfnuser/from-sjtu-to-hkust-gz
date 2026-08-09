import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from route_planner.manifest import build_manifest, load_manifest
from tests.test_export import _segment


class ManifestRerouteMetadataTests(unittest.TestCase):
    def test_round_trip_preserves_reviewed_reroute_decision(self):
        original = _segment()
        segment = replace(
            original,
            rule=replace(
                original.rule,
                reroute_status="manual_review",
                reroute_reason="替代县道未确认连续铺装。",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(
                json.dumps(build_manifest("route-test", [segment]), ensure_ascii=False),
                encoding="utf-8",
            )

            loaded = load_manifest(path, "route-test")[0]

        self.assertEqual(loaded.rule.reroute_status, "manual_review")
        self.assertEqual(loaded.rule.reroute_reason, "替代县道未确认连续铺装。")

    def test_old_manifest_without_decision_fields_defaults_to_unreviewed(self):
        manifest = build_manifest("route-test", [_segment()])
        rule = manifest["segments"][0]["rule"]
        rule.pop("reroute_status", None)
        rule.pop("reroute_reason", None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            loaded = load_manifest(path, "route-test")[0]

        self.assertEqual(loaded.rule.reroute_status, "unreviewed")
        self.assertEqual(loaded.rule.reroute_reason, "")


if __name__ == "__main__":
    unittest.main()
