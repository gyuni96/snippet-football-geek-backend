import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from app.jobs.run_briefing import run_pipeline


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

    def test_run_pipeline_uses_rss_url_when_provided(self):
        sample_feed_item = _sample_raw_item()

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[sample_feed_item]) as collector:
            payload = run_pipeline(
                team_slug="liverpool",
                briefing_type="morning",
                rss_url="https://example.com/rss",
                rss_source_name="Example RSS",
            )

        collector.assert_called_once_with(
            feed_url="https://example.com/rss",
            team_slug="liverpool",
            source_name="Example RSS",
        )
        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_urls, ["https://example.com/liverpool-story"])


def _sample_raw_item():
    from datetime import datetime, timezone

    from app.models import RawItem

    return RawItem(
        team_slug="liverpool",
        source_type="rss",
        source_name="Example RSS",
        external_id="rss-1",
        url="https://example.com/liverpool-story",
        title="Liverpool transfer update",
        text="Liverpool are monitoring a transfer target.",
        published_at=datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc),
    )


if __name__ == "__main__":
    unittest.main()
