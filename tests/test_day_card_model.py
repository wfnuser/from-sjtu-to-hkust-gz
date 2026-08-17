import json
from pathlib import Path
import subprocess
import unittest


class DayCardModelTests(unittest.TestCase):
    def test_visible_itinerary_starts_at_day_one(self):
        days = [{"day": day} for day in range(16)]
        script = """
          import { visibleItineraryDays } from './web/day-card-model.mjs';
          console.log(JSON.stringify(visibleItineraryDays({
            display_start_day: 1,
            days: JSON.parse(process.argv[1]),
          })));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script, json.dumps(days)],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [day["day"] for day in json.loads(result.stdout)],
            list(range(1, 16)),
        )

    def test_visible_route_features_exclude_days_before_public_start(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {"properties": {"day_id": 0, "segment_id": "history"}},
                {"properties": {"day_id": 1, "segment_id": "public"}},
            ],
        }
        script = """
          import { visibleRouteFeatures } from './web/day-card-model.mjs';
          const geojson = JSON.parse(process.argv[1]);
          const itinerary = { display_start_day: 1 };
          console.log(JSON.stringify(visibleRouteFeatures(geojson, itinerary)));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script, json.dumps(geojson)],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [feature["properties"]["segment_id"] for feature in payload["features"]],
            ["public"],
        )

    def test_day_card_keeps_decision_fields_visible(self):
        day = {
            "day": 3,
            "status": "planned",
            "from_name": "桐乡酒店",
            "to_name": "西溪亚朵S",
            "distance_m": 70_406,
            "duration_s": 13_735,
            "key_waypoints": ["阿里巴巴西溪园区"],
            "risk_note": "白天通过",
            "lodging": {"name": "西溪亚朵S", "laundry": "confirmed"},
        }
        script = """
          import { dayCardModel } from './web/day-card-model.mjs';
          console.log(JSON.stringify(dayCardModel(JSON.parse(process.argv[1]))));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script, json.dumps(day, ensure_ascii=False)],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        model = json.loads(result.stdout)
        self.assertEqual(model["label"], "day3")
        self.assertEqual(model["distance"], "70.4 km")
        self.assertEqual(model["route"], "桐乡酒店 → 西溪亚朵S")
        self.assertEqual(model["title"], "day3 桐乡酒店 → 西溪亚朵S")
        self.assertEqual(model["waypoints"], ["阿里巴巴西溪园区"])
        self.assertEqual(model["lodging"], "西溪亚朵S")
        self.assertTrue(model["laundryConfirmed"])
        self.assertEqual(model["riskNote"], "白天通过")


if __name__ == "__main__":
    unittest.main()
