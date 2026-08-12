from pathlib import Path
import re
import unittest


class WebMapContractTests(unittest.TestCase):
    @staticmethod
    def css_block(css, selector):
        match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}", css, re.DOTALL)
        if match is None:
            raise AssertionError(f"Missing CSS block for {selector}")
        return match.group("body")

    @staticmethod
    def media_block(css, max_width):
        start = css.index(f"@media (max-width: {max_width}px)")
        opening_brace = css.index("{", start)
        depth = 0
        for index in range(opening_brace, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    return css[opening_brace + 1:index]
        raise AssertionError(f"Unclosed media block for {max_width}px")

    def test_map_uses_compact_overlay_legend_and_nested_scrolling(self):
        html = Path("web/index.html").read_text(encoding="utf-8")
        css = Path("web/styles.css").read_text(encoding="utf-8")
        map_pane = re.search(
            r'<section class="map-pane"[^>]*>(?P<contents>.*?)</section>',
            html,
            re.DOTALL,
        )

        self.assertIn('<section class="map-legend"', html)
        self.assertNotIn('<section class="panel legend"', html)
        self.assertIsNotNone(map_pane)
        self.assertIn('<section class="map-legend"', map_pane.group("contents"))
        self.assertIn("height: 100dvh", css)
        self.assertIn("overflow: hidden", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("grid-template-columns: repeat(2, max-content)", css)
        self.assertIn("pointer-events: none", self.css_block(css, ".map-legend"))

        narrow_css = self.media_block(css, 860)
        narrow_app = self.css_block(narrow_css, ".route-app")
        self.assertIn("grid-template-rows: 52dvh 48dvh", narrow_app)
        self.assertIn("grid-template-areas", narrow_app)
        self.assertIn('"map"', narrow_app)
        self.assertIn('"sidebar"', narrow_app)
        narrow_sidebar = self.css_block(narrow_css, ".sidebar")
        self.assertIn("grid-area: sidebar", narrow_sidebar)
        self.assertIn("padding-bottom: calc(18px + env(safe-area-inset-bottom))", narrow_sidebar)
        self.assertIn("height: 48dvh", narrow_sidebar)
        self.assertIn("grid-area: map", self.css_block(narrow_css, ".map-pane"))
        self.assertIn("height: 52dvh", self.css_block(narrow_css, ".map-pane"))
        self.assertIn("min-height: 44px", self.css_block(narrow_css, ".segment-card, .review-link"))
        narrow_message = self.css_block(narrow_css, ".map-message")
        self.assertIn("top: auto", narrow_message)
        self.assertIn("bottom: 28px", narrow_message)

        compact_css = self.media_block(css, 420)
        self.assertIn("grid-template-columns: repeat(2, max-content)", self.css_block(compact_css, ".map-legend ul"))

    def test_map_has_chinese_controls_and_no_embedded_amap_key(self):
        """Would fail if the public map lost branch controls or exposed a map key."""
        html = Path("web/index.html").read_text(encoding="utf-8")
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("内陆主线", html)
        self.assertIn("宇宙 eBike 骑行路线（江西线）", html)
        self.assertIn("上海交通大学 → 香港科技大学（广州）", html)
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
        self.assertIn("summary.segment_days", js)

    def test_map_renders_an_infeasible_schedule_as_a_decision_warning(self):
        """Would fail if an over-limit schedule were presented as a daily itinerary."""
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("需要 ${dayCount} 天 · 上限 ${maxDays} 天", js)
        self.assertIn(
            "当前路线需要 ${dayCount} 个骑行日，超过 ${maxDays} 天上限 ${dayCount - maxDays} 天；不作为执行方案。",
            js,
        )
        self.assertIn("if (!deadlineFeasible)", js)

    def test_map_omits_day_headings_when_the_schedule_is_infeasible(self):
        """Would fail if road cards were grouped into a non-executable day plan."""
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("const deadlineFeasible = summary.schedule?.deadline_feasible === true", js)
        self.assertIn("if (deadlineFeasible && !entry.optional", js)

    def test_map_publishes_provisional_limits_and_practical_day_duration(self):
        html = Path("web/index.html").read_text(encoding="utf-8")
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn('id="route-limitations"', html)
        self.assertIn('id="daily-schedule"', html)
        self.assertIn("blank_name_distance_m", js)
        self.assertIn("unknown_percent", js)
        self.assertIn("quota_limited_probes", js)
        self.assertIn("duration_limit_met", js)
        self.assertIn("自动检查通过（仍需道路级复核）", js)
        self.assertIn("阻断：不得作为可骑行路线发布", js)
        self.assertIn('risk_tags.includes("freight")', js)
        self.assertNotIn('approved: "已通过"', js)

    def test_map_deduplicates_segment_level_reviews_but_keeps_hard_steps(self):
        js = Path("web/app.mjs").read_text(encoding="utf-8")

        self.assertIn("reviewFeaturesForEntry", js)
        self.assertIn("hardFeatures.length ? hardFeatures : pending.slice(0, 1)", js)

    def test_map_keeps_original_routes_and_exposes_safety_detour_overlays(self):
        html = Path("web/index.html").read_text(encoding="utf-8")
        js = Path("web/app.mjs").read_text(encoding="utf-8")
        css = Path("web/styles.css").read_text(encoding="utf-8")
        profiles = Path("web/route-profile.mjs").read_text(encoding="utf-8")

        self.assertIn('id="reroute-options"', html)
        self.assertIn('id="reroute-summary"', html)
        self.assertIn("避国道备选", html)
        self.assertIn("原路线保留", html)
        self.assertIn("inland-reroute-options.geojson", profiles)
        self.assertIn("addRerouteOptions", js)
        self.assertIn("national_reduction_m", js)
        self.assertIn("distance_delta_m", js)
        self.assertIn("duration_delta_s", js)
        self.assertIn("selection_summary", js)
        self.assertIn("推荐候选", js)
        self.assertIn("需复核候选", js)
        self.assertIn("alternative", css)
        self.assertIn("border-top-style: dashed", css)


if __name__ == "__main__":
    unittest.main()
