from pathlib import Path
import unittest


class WebMapContractTests(unittest.TestCase):
    def test_map_has_chinese_controls_and_no_embedded_amap_key(self):
        """Would fail if the public map lost branch controls or exposed a map key."""
        html = Path("web/index.html").read_text(encoding="utf-8")
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("沿海主线", html)
        self.assertIn("宁波支线", html)
        self.assertIn("深圳支线", html)
        self.assertNotIn("AMAP_WEB_SERVICE_KEY", html + js)

    def test_map_consumes_branch_schema_and_targets_reviewed_step(self):
        """Would fail if branch labels or review links fell back to segment-wide inference."""
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("properties.branch_id", js)
        self.assertNotIn("optionalBranchFor", js)
        self.assertIn("fitReviewFeature", js)
        self.assertIn("路线数据支线标识无效", js)
        self.assertIn("revealReviewBranch", js)
        self.assertIn("elements.ningboCheckbox.checked = true", js)

    def test_map_groups_main_segment_cards_by_assigned_day(self):
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("day-heading", js)
        self.assertIn("第 ${day} 天", js)
        self.assertIn("entry.day", js)


if __name__ == "__main__":
    unittest.main()
