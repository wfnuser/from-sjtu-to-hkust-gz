import json
from pathlib import Path
import tempfile
import unittest

from route_planner.config import load_route_config


class InlandConfigTests(unittest.TestCase):
    def test_inland_corridor_prepends_shanghai_stops_and_preserves_bound_main_ids(self):
        cfg = load_route_config(Path("config/inland-route.json"))
        names = [point.name for point in cfg.waypoints]
        ids = [point.id for point in cfg.waypoints]

        self.assertEqual(
            ids[:8],
            ["pre-01", "pre-02", "pre-03", "pre-04", "pre-05", "pre-06", "pre-07", "main-01"],
        )
        self.assertEqual(
            names[:8],
            [
                "阳曲路",
                "上海交通大学附属中学本部",
                "bilibili 国正中心",
                "大连路地铁站",
                "昌化路649号",
                "京东上海（中海中心）职场",
                "阿里中心（虹桥）",
                "上海交通大学闵行校区",
            ],
        )
        self.assertEqual(names[-1], "香港科技大学（广州）")
        self.assertEqual(ids[-1], "main-27")
        self.assertNotIn("南昌", names)
        self.assertIn("杭州阿里巴巴总部", names)
        self.assertIn("赣州", names)

    def test_published_inland_manifest_keeps_the_sjtu_route_after_the_new_prelude(self):
        manifest = json.loads(
            Path("web/data/inland-route-manifest.json").read_text(encoding="utf-8")
        )
        segment_ids = [segment["segment_id"] for segment in manifest["segments"]]

        self.assertEqual(
            segment_ids[:8],
            [
                "pre-01-to-pre-02",
                "pre-02-to-pre-03",
                "pre-03-to-pre-04",
                "pre-04-to-pre-05",
                "pre-05-to-pre-06",
                "pre-06-to-pre-07",
                "pre-07-to-main-01",
                "main-01-to-main-02",
            ],
        )
        self.assertEqual(segment_ids[-1], "main-26-to-main-27")
        self.assertEqual(len(segment_ids), 33)

    def test_shanghai_prelude_pins_the_two_manually_reviewed_city_candidates(self):
        cfg = load_route_config(Path("config/inland-route.json"))

        self.assertEqual(
            getattr(
                cfg.segment_rules["pre-06-to-pre-07"],
                "preferred_candidate_index",
                None,
            ),
            2,
        )
        self.assertEqual(
            getattr(
                cfg.segment_rules["pre-07-to-main-01"],
                "preferred_candidate_index",
                None,
            ),
            1,
        )

    def test_inland_route_id_rejects_a_deviation_from_the_bound_corridor(self):
        payload = json.loads(Path("config/inland-route.json").read_text(encoding="utf-8"))
        target = next(
            waypoint for waypoint in payload["waypoints"] if waypoint["name"] == "鹰潭"
        )
        target.update(name="南昌", city="南昌", query="南昌")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inland-route.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inland-main corridor"):
                load_route_config(path)


if __name__ == "__main__":
    unittest.main()
