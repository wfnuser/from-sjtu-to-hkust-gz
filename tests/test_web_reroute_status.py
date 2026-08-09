import json
from pathlib import Path
import subprocess
import unittest


class WebRerouteStatusTests(unittest.TestCase):
    def test_status_labels_are_compact_and_unknown_status_stays_hidden(self):
        module = (Path("web/reroute-status.mjs").resolve()).as_uri()
        script = f"""
          import {{ rerouteLabel }} from {json.dumps(module)};
          console.log(JSON.stringify([
            rerouteLabel('adopted'),
            rerouteLabel('rejected'),
            rerouteLabel('manual_review'),
            rerouteLabel('unreviewed'),
            rerouteLabel('unexpected')
          ]));
        """

        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            ["已绕行", "保留原线", "需人工复核", "", ""],
        )


if __name__ == "__main__":
    unittest.main()
