import json
from pathlib import Path
import unittest

from route_planner.config import load_route_config


class ExecutionItineraryContractTests(unittest.TestCase):
    route_path = Path("config/inland-execution-route.json")
    itinerary_path = Path("config/inland-itinerary.json")

    def setUp(self):
        self.assertTrue(self.route_path.exists(), "execution route config must be published")
        self.assertTrue(self.itinerary_path.exists(), "execution itinerary must be published")
        self.route = load_route_config(self.route_path)
        self.itinerary = json.loads(self.itinerary_path.read_text(encoding="utf-8"))

    def test_fixed_actual_and_planned_days_are_not_reassigned(self):
        days = self.itinerary["days"]

        self.assertEqual([day["day"] for day in days], list(range(16)))
        self.assertEqual(days[0]["from_name"], "阳曲路")
        self.assertEqual(days[0]["to_name"], "上海交通大学闵行校区")
        self.assertEqual(days[1]["to_name"], "桐乡万象汇振兴西路亚朵酒店")
        self.assertTrue(any("叶新公路" in name for name in days[1]["key_waypoints"]))
        self.assertEqual(days[2]["status"], "stay")
        self.assertEqual(days[2]["distance_m"], 0)
        self.assertEqual(days[2]["segments"], [])
        self.assertEqual(days[3]["key_waypoints"], ["阿里巴巴西溪园区"])
        self.assertEqual(days[3]["to_name"], "杭州阿里巴巴西溪园区爱橙街亚朵S酒店")
        self.assertEqual(days[15]["to_name"], "香港科技大学（广州）")

    def test_every_execution_segment_is_assigned_to_exactly_one_riding_day(self):
        expected = [
            f"{start.id}-to-{end.id}"
            for start, end in zip(self.route.waypoints, self.route.waypoints[1:])
        ]
        assigned = [
            segment_id
            for day in self.itinerary["days"]
            for segment_id in day["segments"]
        ]

        self.assertEqual(assigned, expected)
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(
            [self.route.segment_rules[segment_id].day for segment_id in expected],
            [day["day"] for day in self.itinerary["days"] for _ in day["segments"]],
        )

    def test_every_planned_night_before_arrival_has_laundry_evidence(self):
        planned_nights = self.itinerary["days"][3:15]

        for day in planned_nights:
            with self.subTest(day=day["day"]):
                lodging = day["lodging"]
                self.assertTrue(lodging["name"])
                self.assertEqual(lodging["laundry"], "confirmed")
                self.assertTrue(lodging["evidence_url"].startswith("https://"))
                self.assertEqual(lodging["booking_status"], "candidate")


if __name__ == "__main__":
    unittest.main()
