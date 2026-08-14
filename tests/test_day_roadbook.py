import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


class DayRoadbookTests(unittest.TestCase):
    def test_day1_export_uses_yexin_road_and_ends_at_tongxiang_hotel(self):
        from scripts.export_day_roadbook import export_day

        geojson = json.loads(
            Path("web/data/inland-execution-route.geojson").read_text(encoding="utf-8")
        )
        itinerary = json.loads(
            Path("web/data/inland-itinerary.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            gpx_path, markdown_path = export_day(
                geojson, itinerary, 1, Path(directory)
            )
            gpx_text = gpx_path.read_text(encoding="utf-8")
            markdown = markdown_path.read_text(encoding="utf-8")
            root = ET.fromstring(gpx_text)
            namespace = {"g": "http://www.topografix.com/GPX/1/1"}
            waypoint_names = [
                item.text for item in root.findall("g:wpt/g:name", namespace)
            ]

        self.assertIn("叶新公路东段", waypoint_names)
        self.assertIn("叶新公路西段", waypoint_names)
        self.assertEqual(waypoint_names[-1], "桐乡万象汇振兴西路亚朵酒店")
        self.assertIn("叶新公路", gpx_text + markdown)
        self.assertNotIn("漕泾", gpx_text + markdown)
        self.assertIn("111.6 km", markdown)


if __name__ == "__main__":
    unittest.main()
