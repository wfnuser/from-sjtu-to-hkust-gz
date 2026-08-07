import json
from pathlib import Path
import tempfile
import unittest

from route_planner.artifacts import ArtifactPaths
from scripts.generate_route import write_artifacts


class ArtifactPathsTests(unittest.TestCase):
    def test_inland_artifact_names_are_independent(self):
        paths = ArtifactPaths.for_profile(Path("web/data"), "inland")

        self.assertEqual(paths.geojson.name, "inland-route.geojson")
        self.assertEqual(paths.summary.name, "inland-summary.json")
        self.assertEqual(paths.review.name, "inland-review.md")
        self.assertEqual(paths.manifest.name, "inland-route-manifest.json")

    def test_coastal_artifact_names_remain_the_legacy_contract(self):
        paths = ArtifactPaths.for_profile(Path("web/data"), "coastal")

        self.assertEqual(paths.geojson.name, "coastal-route.geojson")
        self.assertEqual(paths.summary.name, "summary.json")
        self.assertEqual(paths.review.name, "review.md")
        self.assertEqual(paths.manifest.name, "route-manifest.json")

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported route profile: mountain"):
            ArtifactPaths.for_profile(Path("web/data"), "mountain")


class ArtifactPublicationTests(unittest.TestCase):
    def test_inland_publication_does_not_modify_coastal_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            coastal = ArtifactPaths.for_profile(output_dir, "coastal")
            original_coastal_bytes = {
                path: f"legacy {path.name}".encode("utf-8")
                for path in (coastal.geojson, coastal.summary, coastal.review, coastal.manifest)
            }
            for path, content in original_coastal_bytes.items():
                path.write_bytes(content)

            write_artifacts(
                output_dir,
                {"type": "FeatureCollection", "features": []},
                {"main": {"distance_m": 0}},
                "# Inland review\n",
                {"schema_version": 1, "route_id": "inland-test", "segments": []},
                profile="inland",
            )

            self.assertEqual(
                {path: path.read_bytes() for path in original_coastal_bytes},
                original_coastal_bytes,
            )
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                [
                    "coastal-route.geojson",
                    "inland-review.md",
                    "inland-route-manifest.json",
                    "inland-route.geojson",
                    "inland-summary.json",
                    "review.md",
                    "route-manifest.json",
                    "summary.json",
                ],
            )
            self.assertEqual(
                json.loads(ArtifactPaths.for_profile(output_dir, "inland").summary.read_text()),
                {"main": {"distance_m": 0}},
            )


if __name__ == "__main__":
    unittest.main()
