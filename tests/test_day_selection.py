import json
from pathlib import Path
import subprocess
import unittest


class DaySelectionTests(unittest.TestCase):
    @staticmethod
    def run_node(expression, *arguments):
        script = f"""
          import {{ nextSelectedDayId, routeStyleForSelectedDay }} from './web/day-selection.mjs';
          const args = JSON.parse(process.argv[1]);
          console.log(JSON.stringify({expression}));
        """
        result = subprocess.run(
            [
                "node",
                "--input-type=module",
                "--eval",
                script,
                json.dumps(arguments),
            ],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    def test_clicking_selected_day_clears_selection_while_other_days_switch(self):
        self.assertEqual(self.run_node("nextSelectedDayId(args[0], args[1])", None, 4), 4)
        self.assertEqual(self.run_node("nextSelectedDayId(args[0], args[1])", 4, 5), 5)
        self.assertIsNone(self.run_node("nextSelectedDayId(args[0], args[1])", 4, 4))

    def test_selected_day_is_emphasized_and_other_main_days_are_dimmed(self):
        base_style = {"color": "#2563eb", "weight": 4, "opacity": 0.9}
        selected = self.run_node(
            "routeStyleForSelectedDay(args[0], args[1], args[2])",
            {"properties": {"day_id": 4}},
            4,
            base_style,
        )
        dimmed = self.run_node(
            "routeStyleForSelectedDay(args[0], args[1], args[2])",
            {"properties": {"day_id": 5}},
            4,
            base_style,
        )

        self.assertEqual(selected["color"], "#2563eb")
        self.assertGreaterEqual(selected["weight"], 6)
        self.assertEqual(selected["opacity"], 1)
        self.assertEqual(dimmed["color"], "#2563eb")
        self.assertLessEqual(dimmed["opacity"], 0.2)

    def test_no_selection_and_optional_branches_keep_the_base_style(self):
        base_style = {"color": "#64748b", "weight": 4, "opacity": 0.9, "dashArray": "8 7"}
        without_selection = self.run_node(
            "routeStyleForSelectedDay(args[0], args[1], args[2])",
            {"properties": {"day_id": 4}},
            None,
            base_style,
        )
        optional = self.run_node(
            "routeStyleForSelectedDay(args[0], args[1], args[2])",
            {"properties": {"day_id": 5, "optional_branch": True}},
            4,
            base_style,
        )

        self.assertEqual(without_selection, base_style)
        self.assertEqual(optional, base_style)


if __name__ == "__main__":
    unittest.main()
