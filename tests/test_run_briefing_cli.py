import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
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

    def test_run_pipeline_collects_configured_sources_and_filters_since(self):
        fresh_item = _sample_raw_item(
            external_id="fresh",
            url="https://example.com/fresh-liverpool-story",
            published_at="2026-06-06T09:00:00Z",
        )
        old_item = _sample_raw_item(
            external_id="old",
            url="https://example.com/old-liverpool-story",
            published_at="2026-06-05T09:00:00Z",
        )

        def fake_collect_rss_items(feed_url, team_slug, source_name):
            if "liverpoolecho" in feed_url:
                return [fresh_item, old_item]
            return []

        with patch("app.jobs.run_briefing.collect_rss_items", side_effect=fake_collect_rss_items):
            payload = run_pipeline(
                team_slug="liverpool",
                briefing_type="morning",
                source_keys=["liverpool_echo", "official_website"],
                since_text="2026-06-06T08:00:00Z",
                retention_days=7,
                now_text="2026-06-06T12:00:00Z",
            )

        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_urls, ["https://example.com/fresh-liverpool-story"])

    def test_run_pipeline_uses_state_file_since_and_updates_state(self):
        fresh_item = _sample_raw_item(
            external_id="fresh",
            url="https://example.com/fresh-liverpool-story",
            published_at="2026-06-06T09:00:00Z",
        )
        old_item = _sample_raw_item(
            external_id="old",
            url="https://example.com/old-liverpool-story",
            published_at="2026-06-06T07:00:00Z",
        )

        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            state_file.write_text(
                json.dumps({"last_success_at": "2026-06-06T08:00:00+00:00"}),
                encoding="utf-8",
            )

            with patch("app.jobs.run_briefing.collect_rss_items", return_value=[fresh_item, old_item]):
                payload = run_pipeline(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["liverpool_echo"],
                    retention_days=7,
                    now_text="2026-06-06T12:00:00Z",
                    state_file=state_file,
                )

            saved_state = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_urls, ["https://example.com/fresh-liverpool-story"])
        self.assertEqual(saved_state["last_success_at"], "2026-06-06T12:00:00+00:00")

    def test_run_pipeline_uses_groq_summarizer_when_enabled(self):
        sample_feed_item = _sample_raw_item()

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[sample_feed_item]):
            with patch("app.jobs.run_briefing.build_article_summarizer") as factory:
                factory.return_value = lambda article: {
                    "headline_ko": "그록 헤드라인",
                    "body_ko": "그록 요약 본문",
                    "confidence_label": "reported",
                }
                payload = run_pipeline(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["liverpool_echo"],
                    use_groq=True,
                    groq_api_key="test-key",
                    groq_model="test-model",
                    now_text="2026-06-06T12:00:00Z",
                )

        factory.assert_called_once_with(api_key="test-key", model="test-model")
        self.assertEqual(payload.items[0].headline_ko, "그록 헤드라인")
        self.assertEqual(payload.items[0].body_ko, "그록 요약 본문")

    def test_run_pipeline_limits_relevant_items_before_groq_summarization(self):
        first = _sample_raw_item(
            external_id="first",
            url="https://example.com/first-liverpool-story",
        )
        second = _sample_raw_item(
            external_id="second",
            url="https://example.com/second-liverpool-story",
        )
        third = _sample_raw_item(
            external_id="third",
            url="https://example.com/third-liverpool-story",
        )
        summarized_urls = []

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[first, second, third]):
            with patch("app.jobs.run_briefing.build_article_summarizer") as factory:
                def fake_summarizer(article):
                    summarized_urls.append(article.canonical_url)
                    return {
                        "headline_ko": f"요약 {article.external_id}",
                        "body_ko": "제한된 항목만 요약합니다.",
                        "confidence_label": "reported",
                    }

                factory.return_value = fake_summarizer
                payload = run_pipeline(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["liverpool_echo"],
                    use_groq=True,
                    groq_api_key="test-key",
                    groq_model="test-model",
                    limit=2,
                    now_text="2026-06-06T12:00:00Z",
                )

        self.assertEqual(len(payload.items), 2)
        self.assertEqual(
            summarized_urls,
            [
                "https://example.com/first-liverpool-story",
                "https://example.com/second-liverpool-story",
            ],
        )


def _sample_raw_item(
    external_id="rss-1",
    url="https://example.com/liverpool-story",
    published_at="2026-06-06T08:00:00Z",
):
    from datetime import datetime, timezone

    from app.models import RawItem

    parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(timezone.utc)

    return RawItem(
        team_slug="liverpool",
        source_type="rss",
        source_name="Example RSS",
        external_id=external_id,
        url=url,
        title="Liverpool transfer update",
        text="Liverpool are monitoring a transfer target.",
        published_at=parsed,
    )


if __name__ == "__main__":
    unittest.main()
