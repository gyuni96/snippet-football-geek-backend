import json
import subprocess
import sys
import unittest


class RunBriefingCliTest(unittest.TestCase):
    def test_cli_prints_briefing_payload_as_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.jobs.run_briefing",
                "--team",
                "liverpool",
                "--type",
                "morning",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)

        self.assertEqual(payload["team_slug"], "liverpool")
        self.assertEqual(payload["briefing_type"], "morning")
        self.assertEqual(payload["title"], "리버풀 아침 브리핑")
        self.assertGreaterEqual(len(payload["items"]), 2)
        self.assertIn("published_at", payload)


if __name__ == "__main__":
    unittest.main()
