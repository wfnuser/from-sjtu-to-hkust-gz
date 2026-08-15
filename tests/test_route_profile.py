import json
from pathlib import Path
import subprocess
import unittest


class RouteProfileTests(unittest.TestCase):
    def select_profile(self, search: str) -> dict[str, object]:
        script = """
          import { selectRouteProfile } from './web/route-profile.mjs';
          console.log(JSON.stringify(selectRouteProfile(process.argv[1])));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script, search],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_empty_query_opens_the_execution_itinerary(self):
        profile = self.select_profile("")

        self.assertEqual(profile["id"], "execution")
        self.assertEqual(profile["geojsonUrl"], "data/inland-execution-route.geojson")
        self.assertEqual(profile["summaryUrl"], "data/inland-execution-summary.json")
        self.assertEqual(profile["itineraryUrl"], "data/inland-itinerary.json")
        self.assertEqual(profile["title"], "宇宙骑行路线（江西线）")
        self.assertEqual(profile["mainLabel"], "Day 1–15 执行路线")
        self.assertFalse(profile["hasOptionalBranches"])
        self.assertIs(profile.get("showSchedule"), False)

    def test_coastal_query_keeps_the_existing_coastal_artifacts(self):
        profile = self.select_profile("?route=coastal")

        self.assertEqual(profile["id"], "coastal")
        self.assertEqual(profile["geojsonUrl"], "data/coastal-route.geojson")
        self.assertEqual(profile["summaryUrl"], "data/summary.json")
        self.assertEqual(profile["title"], "沿海骑行路线")
        self.assertTrue(profile["hasOptionalBranches"])
        self.assertIs(profile.get("showSchedule"), True)

    def test_unknown_profile_falls_back_to_inland(self):
        self.assertEqual(self.select_profile("?route=unknown")["id"], "execution")


if __name__ == "__main__":
    unittest.main()
