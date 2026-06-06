import json
from pathlib import Path
import subprocess
import sys
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, patch

from app.collectors.x_profiles import XProfileCollectionError
from app.jobs.run_briefing import (
    is_x_auth_issue,
    main,
    PipelineDiagnostics,
    resolve_since_text,
    run_pipeline,
    run_pipeline_with_diagnostics,
    should_save_payload_to_supabase,
)
from app.models import BriefingPayload
from app.sources import LIVERPOOL_X_PROFILES


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
            with patch("app.jobs.run_briefing.collect_html_listing_items", return_value=[]):
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

    def test_run_pipeline_collects_html_listing_source_as_articles(self):
        listing_item = _sample_raw_item(
            external_id="official-story",
            url="https://www.liverpoolfc.com/news/official-liverpool-story",
            source_type="html_listing",
            source_name="Liverpool FC Official Website",
            published_at="2026-06-06T09:00:00Z",
        )

        with patch("app.jobs.run_briefing.collect_html_listing_items", return_value=[listing_item]) as collector:
            payload = run_pipeline(
                team_slug="liverpool",
                briefing_type="morning",
                source_keys=["official_website"],
                retention_days=7,
                now_text="2026-06-06T12:00:00Z",
            )

        collector.assert_called_once_with(
            listing_url="https://www.liverpoolfc.com/news",
            team_slug="liverpool",
            source_name="Liverpool FC Official Website",
            required_terms=(),
        )
        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_type, "article")
        self.assertEqual(payload.items[0].source_urls, ["https://www.liverpoolfc.com/news/official-liverpool-story"])

    def test_run_pipeline_collects_x_profile_sources_as_social_posts(self):
        x_item = _sample_raw_item(
            external_id="post-1",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at="2026-06-06T09:00:00Z",
            source_type="x_profile",
            source_name="James Pearce",
            author="JamesPearceLFC",
        )

        with patch("app.jobs.run_briefing.collect_x_profile_items", return_value=[x_item]) as collector:
            payload = run_pipeline(
                team_slug="liverpool",
                briefing_type="morning",
                source_keys=["x_reporters"],
                retention_days=7,
                now_text="2026-06-06T12:00:00Z",
            )

        self.assertEqual(collector.call_count, len(LIVERPOOL_X_PROFILES))
        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_type, "social_post")
        self.assertEqual(payload.items[0].source_urls, ["https://x.com/JamesPearceLFC/status/post-1"])

    def test_run_pipeline_keeps_rss_items_when_x_collection_fails(self):
        rss_item = _sample_raw_item()
        stderr = StringIO()

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[rss_item]):
            with patch(
                "app.jobs.run_briefing.collect_x_profile_items",
                side_effect=XProfileCollectionError("X login blocked"),
            ):
                with patch("sys.stderr", stderr):
                    payload = run_pipeline(
                        team_slug="liverpool",
                        briefing_type="morning",
                        source_keys=["liverpool_echo", "x_reporters"],
                        retention_days=7,
                        now_text="2026-06-06T12:00:00Z",
                    )

        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_urls, ["https://example.com/liverpool-story"])
        self.assertIn("X collection skipped", stderr.getvalue())
        self.assertIn("X login blocked", stderr.getvalue())

    def test_run_pipeline_diagnostics_tracks_x_auth_issue_handles(self):
        rss_item = _sample_raw_item()
        stderr = StringIO()

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[rss_item]):
            with patch(
                "app.jobs.run_briefing.collect_x_profile_items",
                side_effect=XProfileCollectionError("401 Unauthorized: auth_token cookie expired"),
            ):
                with patch("sys.stderr", stderr):
                    payload, diagnostics = run_pipeline_with_diagnostics(
                        team_slug="liverpool",
                        briefing_type="morning",
                        source_keys=["liverpool_echo", "x_reporters"],
                        retention_days=7,
                        now_text="2026-06-06T12:00:00Z",
                    )

        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertIn("JamesPearceLFC", diagnostics.x_auth_issue_handles)
        self.assertIn("auth_token cookie expired", stderr.getvalue())

    def test_main_saves_warning_monitoring_status_for_partial_collection(self):
        from datetime import datetime, timezone

        payload = BriefingPayload(
            team_slug="liverpool",
            briefing_type="morning",
            title="리버풀 아침 브리핑",
            summary_ko="출근길에 확인할 리버풀 핵심 소식 0건입니다.",
            published_at=datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc),
            items=[],
        )
        diagnostics = PipelineDiagnostics(
            article_attempted=True,
            article_succeeded=True,
            x_attempted=True,
            x_failed=True,
        )

        with patch("sys.argv", ["run_briefing", "--team", "liverpool", "--type", "morning", "--save-monitoring"]):
            with patch("app.jobs.run_briefing.load_env_file"):
                with patch("app.jobs.run_briefing.run_pipeline_with_diagnostics", return_value=(payload, diagnostics)):
                    with patch("app.jobs.run_briefing.save_monitoring_run") as save_monitoring:
                        with patch("sys.stdout", StringIO()):
                            main()

        self.assertEqual(save_monitoring.call_args.kwargs["status"], "warning")

    def test_pipeline_diagnostics_reports_warning_when_only_x_fails(self):
        diagnostics = PipelineDiagnostics(
            article_attempted=True,
            article_succeeded=True,
            x_attempted=True,
            x_failed=True,
        )

        self.assertEqual(diagnostics.notification_status(), "warning")

    def test_pipeline_diagnostics_reports_warning_when_groq_limit_is_detected(self):
        sample_feed_item = _sample_raw_item()

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[sample_feed_item]):
            with patch("app.jobs.run_briefing.summarize_article_with_groq") as summarize:
                summarize.side_effect = (
                    RuntimeError("Groq daily token limit has been reached; skipping remaining Groq requests.")
                )
                payload, diagnostics = run_pipeline_with_diagnostics(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["liverpool_echo"],
                    use_groq=True,
                    groq_api_key="test-key",
                    now_text="2026-06-06T12:00:00Z",
                )

        self.assertEqual(payload.items, [])
        self.assertEqual(diagnostics.notification_status(), "warning")
        self.assertEqual(
            diagnostics.groq_issue_messages,
            ["Groq daily token limit has been reached; skipping remaining Groq requests."],
        )

    def test_pipeline_diagnostics_reports_failed_when_articles_and_x_fail(self):
        diagnostics = PipelineDiagnostics(
            article_attempted=True,
            article_failed=True,
            x_attempted=True,
            x_failed=True,
        )

        self.assertEqual(diagnostics.notification_status(), "failed")

    def test_pipeline_diagnostics_reports_success_when_articles_and_x_succeed(self):
        diagnostics = PipelineDiagnostics(
            article_attempted=True,
            article_succeeded=True,
            x_attempted=True,
            x_succeeded=True,
        )

        self.assertEqual(diagnostics.notification_status(), "success")

    def test_is_x_auth_issue_detects_expired_token_errors(self):
        self.assertTrue(is_x_auth_issue("401 Unauthorized: auth_token cookie expired"))
        self.assertTrue(is_x_auth_issue("Forbidden because ct0 token is invalid"))
        self.assertFalse(is_x_auth_issue("profile timeline returned no tweets"))

    def test_run_pipeline_keeps_other_sources_when_one_rss_source_fails(self):
        rss_item = _sample_raw_item()
        stderr = StringIO()

        def fake_collect_rss_items(feed_url, team_slug, source_name):
            if "liverpoolecho" in feed_url:
                return [rss_item]
            raise RuntimeError("RSS certificate failed")

        sources = [
            SimpleNamespace(key="working_rss", rss_url="https://example.com/liverpoolecho/rss", name="Working RSS"),
            SimpleNamespace(key="broken_rss", rss_url="https://example.com/broken/rss", name="Broken RSS"),
        ]
        with patch("app.jobs.run_briefing.iter_collectable_sources", return_value=sources):
            with patch("app.jobs.run_briefing.iter_collectable_x_profiles", return_value=[]):
                with patch("app.jobs.run_briefing.collect_rss_items", side_effect=fake_collect_rss_items):
                    with patch("sys.stderr", stderr):
                        payload = run_pipeline(
                            team_slug="liverpool",
                            briefing_type="morning",
                            source_keys=["all"],
                            retention_days=7,
                            now_text="2026-06-06T12:00:00Z",
                        )

        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 1건입니다.")
        self.assertEqual(payload.items[0].source_urls, ["https://example.com/liverpool-story"])
        self.assertIn("RSS collection skipped", stderr.getvalue())
        self.assertIn("RSS certificate failed", stderr.getvalue())

    def test_cli_supports_x_provider_option(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.jobs.run_briefing",
                "--help",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("--x-provider", completed.stdout)
        self.assertIn("--x-storage-state", completed.stdout)
        self.assertIn("twikit", completed.stdout)
        self.assertIn("--x-cookies-file", completed.stdout)

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

        factory.assert_called_once_with(
            api_key="test-key",
            model="test-model",
            rate_limiter=ANY,
            usage_guard=ANY,
            diagnostics=ANY,
        )
        guard = factory.call_args.kwargs["usage_guard"]
        self.assertEqual(guard.max_requests, 60)
        self.assertEqual(guard.request_count, 0)
        self.assertEqual(payload.items[0].headline_ko, "그록 헤드라인")
        self.assertEqual(payload.items[0].body_ko, "그록 요약 본문")

    def test_run_pipeline_uses_configured_groq_max_requests(self):
        sample_feed_item = _sample_raw_item()

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=[sample_feed_item]):
            with patch("app.jobs.run_briefing.build_article_summarizer") as factory:
                factory.return_value = lambda article: {
                    "headline_ko": "그록 헤드라인",
                    "body_ko": "그록 요약 본문",
                    "confidence_label": "reported",
                }
                run_pipeline(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["liverpool_echo"],
                    use_groq=True,
                    groq_api_key="test-key",
                    groq_model="test-model",
                    groq_max_requests=12,
                    now_text="2026-06-06T12:00:00Z",
                )

        factory.assert_called_once_with(
            api_key="test-key",
            model="test-model",
            rate_limiter=ANY,
            usage_guard=ANY,
            diagnostics=ANY,
        )
        self.assertEqual(factory.call_args.kwargs["usage_guard"].max_requests, 12)

    def test_run_pipeline_uses_groq_social_post_summarizer_when_enabled(self):
        x_item = _sample_raw_item(
            external_id="post-1",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at="2026-06-06T09:00:00Z",
            source_type="x_profile",
            source_name="James Pearce",
            author="JamesPearceLFC",
        )

        with patch("app.jobs.run_briefing.collect_x_profile_items", return_value=[x_item]):
            with patch("app.jobs.run_briefing.build_social_post_summarizer") as factory:
                factory.return_value = lambda post: {
                    "headline_ko": "Pearce, 이적 관련 기자 신호",
                    "body_ko": "James Pearce가 리버풀 이적 관련 흐름을 전했습니다.",
                    "confidence_label": "reporter_claim",
                    "category": "transfer",
                }
                payload = run_pipeline(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["x_reporters"],
                    use_groq=True,
                    groq_api_key="test-key",
                    groq_model="test-model",
                    now_text="2026-06-06T12:00:00Z",
                )

        factory.assert_called_once_with(
            api_key="test-key",
            model="test-model",
            rate_limiter=ANY,
            usage_guard=ANY,
            diagnostics=ANY,
        )
        self.assertEqual(payload.items[0].headline_ko, "Pearce, 이적 관련 기자 신호")
        self.assertEqual(payload.items[0].body_ko, "James Pearce가 리버풀 이적 관련 흐름을 전했습니다.")

    def test_run_pipeline_limits_relevant_items_before_groq_summarization(self):
        first = _sample_raw_item(
            external_id="first",
            url="https://example.com/first-liverpool-story",
            title="Liverpool monitor midfield target",
            text="Liverpool are monitoring a midfield target.",
        )
        second = _sample_raw_item(
            external_id="second",
            url="https://example.com/second-liverpool-story",
            title="Liverpool injury update before derby",
            text="Liverpool have an injury update before the derby.",
        )
        third = _sample_raw_item(
            external_id="third",
            url="https://example.com/third-liverpool-story",
            title="Liverpool academy prospect signs contract",
            text="Liverpool academy prospect signs a new contract.",
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

    def test_run_pipeline_limit_keeps_social_post_when_articles_are_available(self):
        article_items = [
            _sample_raw_item(
                external_id=f"article-{index}",
                url=f"https://example.com/article-{index}",
                title=[
                    "Liverpool monitor midfield target",
                    "Liverpool injury update before derby",
                    "Liverpool academy prospect signs contract",
                    "Liverpool prepare Anfield ticket update",
                    "Liverpool goal of season shortlist revealed",
                ][index],
                text=[
                    "Liverpool are monitoring a midfield target.",
                    "Liverpool have an injury update before the derby.",
                    "Liverpool academy prospect signs a new contract.",
                    "Liverpool prepare an Anfield ticket update.",
                    "Liverpool reveal goal of the season shortlist.",
                ][index],
            )
            for index in range(5)
        ]
        x_item = _sample_raw_item(
            external_id="post-1",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at="2026-06-06T09:00:00Z",
            source_type="x_profile",
            source_name="James Pearce",
            author="JamesPearceLFC",
        )

        with patch("app.jobs.run_briefing.collect_rss_items", return_value=article_items):
            with patch("app.jobs.run_briefing.collect_x_profile_items", return_value=[x_item]):
                payload = run_pipeline(
                    team_slug="liverpool",
                    briefing_type="morning",
                    source_keys=["liverpool_echo", "x_reporters"],
                    retention_days=7,
                    now_text="2026-06-06T12:00:00Z",
                    limit=5,
                )

        self.assertEqual(len(payload.items), 5)
        self.assertEqual(payload.items[-1].source_type, "social_post")
        self.assertEqual(payload.items[-1].source_urls, ["https://x.com/JamesPearceLFC/status/post-1"])

    def test_cli_supports_save_supabase_option(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.jobs.run_briefing",
                "--help",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("--save-supabase", completed.stdout)
        self.assertIn("--save-monitoring", completed.stdout)
        self.assertIn("--notify-discord", completed.stdout)
        self.assertIn("--until", completed.stdout)
        self.assertIn("--now", completed.stdout)
        self.assertIn("--groq-requests-per-minute", completed.stdout)
        self.assertIn("--groq-max-requests", completed.stdout)

    def test_resolve_since_text_uses_latest_supabase_briefing_when_saving(self):
        class FakeClient:
            pass

        client = FakeClient()
        with patch(
            "app.jobs.run_briefing.fetch_latest_briefing_published_at",
            return_value="2026-06-06T09:00:00+00:00",
        ) as fetch_latest:
            since_text = resolve_since_text(
                team_slug="liverpool",
                briefing_type="afternoon",
                explicit_since_text=None,
                state_file=None,
                save_supabase=True,
                supabase_client=client,
            )

        self.assertEqual(since_text, "2026-06-06T09:00:00+00:00")
        fetch_latest.assert_called_once_with(
            client,
            team_slug="liverpool",
        )

    def test_resolve_since_text_keeps_explicit_since_over_supabase_latest(self):
        class FakeClient:
            pass

        with patch("app.jobs.run_briefing.fetch_latest_briefing_published_at") as fetch_latest:
            since_text = resolve_since_text(
                team_slug="liverpool",
                briefing_type="afternoon",
                explicit_since_text="2026-06-06T08:00:00Z",
                state_file=None,
                save_supabase=True,
                supabase_client=FakeClient(),
            )

        self.assertEqual(since_text, "2026-06-06T08:00:00Z")
        fetch_latest.assert_not_called()

    def test_should_not_save_empty_payload_to_supabase(self):
        from datetime import datetime, timezone

        payload = BriefingPayload(
            team_slug="liverpool",
            briefing_type="afternoon",
            title="리버풀 오후 브리핑",
            summary_ko="출근길에 확인할 리버풀 핵심 소식 0건입니다.",
            published_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
            items=[],
        )

        self.assertFalse(should_save_payload_to_supabase(payload))


def _sample_raw_item(
    external_id="rss-1",
    url="https://example.com/liverpool-story",
    published_at="2026-06-06T08:00:00Z",
    source_type="rss",
    source_name="Example RSS",
    author=None,
    title="Liverpool transfer update",
    text="Liverpool are monitoring a transfer target.",
):
    from datetime import datetime, timezone

    from app.models import RawItem

    parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(timezone.utc)

    return RawItem(
        team_slug="liverpool",
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        url=url,
        title=title,
        text=text,
        published_at=parsed,
        author=author,
    )


if __name__ == "__main__":
    unittest.main()
