import json
from pathlib import Path
import tempfile
import unittest

from route_planner.config import load_route_config


class InlandConfigTests(unittest.TestCase):
    def test_inland_corridor_is_chinese_and_excludes_nanchang(self):
        cfg = load_route_config(Path("config/inland-route.json"))
        names = [point.name for point in cfg.waypoints]

        self.assertEqual(names[0], "上海交通大学闵行校区")
        self.assertEqual(names[-1], "香港科技大学（广州）")
        self.assertNotIn("南昌", names)
        self.assertIn("杭州阿里巴巴总部", names)
        self.assertIn("赣州", names)

    def test_inland_route_id_rejects_a_deviation_from_the_bound_corridor(self):
        payload = json.loads(Path("config/inland-route.json").read_text(encoding="utf-8"))
        payload["waypoints"][11].update(name="南昌", city="南昌", query="南昌")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inland-route.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inland-main corridor"):
                load_route_config(path)


if __name__ == "__main__":
    unittest.main()
