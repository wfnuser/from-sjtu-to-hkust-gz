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


if __name__ == "__main__":
    unittest.main()
