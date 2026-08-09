import json
from pathlib import Path
import subprocess
import unittest


class WebRerouteOptionTests(unittest.TestCase):
    def test_original_and_detour_have_distinct_styles_and_full_comparison_copy(self):
        module = (Path("web/reroute-options.mjs").resolve()).as_uri()
        script = f"""
          import {{
            rerouteLineStyle,
            rerouteComparisonText,
            rerouteFeaturesForOption
          }} from {json.dumps(module)};
          const option = {{
            segment_id: 'target',
            candidate_id: 'county-detour',
            current_distance_m: 80000,
            current_national_m: 30000,
            alternative_distance_m: 100000,
            alternative_national_m: 5000,
            distance_delta_m: 20000,
            duration_delta_s: 3600,
            national_reduction_m: 25000
          }};
          const alternativeFeatures = [
            {{ properties: {{ candidate_id: 'county-detour', route_role: 'alternative' }} }},
            {{ properties: {{ candidate_id: 'other', route_role: 'alternative' }} }}
          ];
          const originalFeatures = [
            {{ properties: {{ segment_id: 'target', road_name: 'G105' }} }},
            {{ properties: {{ segment_id: 'another', road_name: '其他道路' }} }}
          ];
          const paired = rerouteFeaturesForOption(option, alternativeFeatures, originalFeatures);
          console.log(JSON.stringify({{
            original: rerouteLineStyle({{ properties: {{ route_role: 'original' }} }}),
            alternative: rerouteLineStyle({{ properties: {{ route_role: 'alternative' }} }}),
            copy: rerouteComparisonText(option),
            paired: paired.map(feature => [
              feature.properties.route_role,
              feature.properties.candidate_id,
              feature.properties.road_name || ''
            ])
          }}));
        """

        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["original"],
            {"color": "#334155", "weight": 7, "opacity": 0.65, "dashArray": "2 8"},
        )
        self.assertEqual(
            payload["alternative"],
            {"color": "#0891b2", "weight": 5, "opacity": 0.9, "dashArray": "10 7"},
        )
        self.assertEqual(
            payload["copy"],
            "原线 80 km（国道 30 km）→ 绕行 100 km（国道 5.0 km）"
            " · 多 20 km / 1 小时 · 少走国道 25 km",
        )
        self.assertEqual(
            payload["paired"],
            [
                ["original", "county-detour", "G105"],
                ["alternative", "county-detour", ""],
            ],
        )


if __name__ == "__main__":
    unittest.main()
