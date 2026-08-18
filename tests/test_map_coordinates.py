import json
from pathlib import Path
import subprocess
import unittest


class MapCoordinateTests(unittest.TestCase):
    module_path = Path("web/map-coordinates.mjs")

    def run_node(self, expression):
        script = f"""
          import {{ wgs84ToGcj02, geojsonWgs84ToGcj02 }} from './{self.module_path.as_posix()}';
          const result = {expression};
          process.stdout.write(JSON.stringify(result));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_converts_a_china_coordinate_for_amap_tiles(self):
        converted = self.run_node("wgs84ToGcj02([121.469, 31.232])")

        self.assertGreater(converted[0], 121.47)
        self.assertGreater(converted[1], 31.23)
        self.assertLess(converted[0], 121.48)
        self.assertLess(converted[1], 31.24)

    def test_leaves_coordinates_outside_china_unchanged(self):
        self.assertEqual(
            self.run_node("wgs84ToGcj02([-73.9857, 40.7484])"),
            [-73.9857, 40.7484],
        )

    def test_transforms_geojson_without_mutating_published_data(self):
        result = self.run_node("""(() => {
          const source = {type: 'Feature', properties: {id: 'road'}, geometry: {
            type: 'LineString', coordinates: [[121.469, 31.232], [121.47, 31.233]]
          }};
          const transformed = geojsonWgs84ToGcj02(source);
          return {source, transformed};
        })()""")

        self.assertEqual(result["source"]["geometry"]["coordinates"][0], [121.469, 31.232])
        self.assertNotEqual(
            result["transformed"]["geometry"]["coordinates"][0],
            result["source"]["geometry"]["coordinates"][0],
        )

