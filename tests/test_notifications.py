import io
import json
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError

from app.models import BriefingItem, BriefingPayload
from app.notifications import DiscordNotifier, build_discord_run_message


class DiscordNotificationTest(unittest.TestCase):
    def test_builds_success_message_from_briefing_payload(self):
        payload = BriefingPayload(
            team_slug="liverpool",
            briefing_type="morning",
            title="리버풀 아침 브리핑",
            summary_ko="출근길에 확인할 리버풀 핵심 소식 2건입니다.",
            published_at=datetime(2026, 6, 7, 5, 0, tzinfo=timezone.utc),
            items=[
                _briefing_item(source_type="article"),
                _briefing_item(source_type="social_post"),
            ],
        )

        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="success",
            source_keys=["all"],
            payload=payload,
            briefing_id="briefing-1",
            github_run_url="https://github.com/example/repo/actions/runs/1",
            x_auth_issue_handles=["JamesPearceLFC", "FabrizioRomano"],
        )

        self.assertEqual(message["content"], "✅ 수집 완료")
        self.assertEqual(message["embeds"][0]["title"], "✅ Liverpool Briefing 수집 성공")
        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(fields["팀"], "liverpool")
        self.assertEqual(fields["브리핑"], "morning")
        self.assertEqual(fields["항목"], "총 2개 / 기사 1개 / X 1개")
        self.assertNotIn("저장", fields)
        self.assertNotIn("소스", fields)
        self.assertEqual(fields["GitHub Actions"], "https://github.com/example/repo/actions/runs/1")
        self.assertEqual(fields["⚠️ X 인증 상태"], "⚠️ 토큰/쿠키 만료 의심: @JamesPearceLFC, @FabrizioRomano")

    def test_omits_x_auth_status_when_no_auth_issue_exists(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="success",
            source_keys=["all"],
            payload=None,
            briefing_id=None,
        )

        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertNotIn("⚠️ X 인증 상태", fields)

    def test_builds_failed_message_with_error_text(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="evening",
            status="failed",
            source_keys=["x_reporters"],
            payload=None,
            briefing_id=None,
            error_message="Groq API failed",
        )

        self.assertEqual(message["content"], "❌ 수집 실패")
        self.assertEqual(message["embeds"][0]["title"], "❌ Liverpool Briefing 수집 실패")
        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(fields["항목"], "총 0개 / 기사 0개 / X 0개")
        self.assertNotIn("저장", fields)
        self.assertNotIn("소스", fields)
        self.assertEqual(fields["오류"], "Groq API failed")

    def test_builds_warning_message_for_partial_collection(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="warning",
            source_keys=["all"],
            payload=None,
            briefing_id=None,
            error_message="X 수집 일부 실패",
        )

        self.assertEqual(message["content"], "⚠️ 부분 수집 완료")
        self.assertEqual(message["embeds"][0]["title"], "⚠️ Liverpool Briefing 부분 수집")
        self.assertEqual(message["embeds"][0]["color"], 0xF1C40F)

    def test_builds_groq_status_field_when_groq_limit_is_detected(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="warning",
            source_keys=["all"],
            payload=None,
            briefing_id=None,
            groq_issue_messages=["Groq daily token limit has been reached; skipping remaining Groq requests."],
        )

        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(
            fields["⚠️ Groq 상태"],
            "⚠️ Groq 일일 토큰 한도 초과로 남은 요약 요청을 건너뜁니다.",
        )

    def test_builds_collection_debug_field_when_counts_are_provided(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="warning",
            source_keys=["all"],
            payload=None,
            briefing_id=None,
            collection_counts={
                "raw_item_count": 42,
                "fresh_item_count": 30,
                "relevant_article_count": 18,
                "relevant_social_post_count": 7,
                "article_candidate_count": 12,
                "social_post_candidate_count": 6,
                "article_output_count": 9,
                "social_post_output_count": 5,
            },
        )

        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(
            fields["📊 수집 흐름"],
            "원본 42개 → 최신 30개\n"
            "관련성 통과: 기사 18개 / X 7개\n"
            "요약 후보: 기사 12개 / X 6개\n"
            "저장 대상: 기사 9개 / X 5개\n"
            "제외/미사용: 기사 3개 / X 1개",
        )

    def test_builds_groq_model_field_when_model_tracking_exists(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="warning",
            source_keys=["all"],
            payload=None,
            briefing_id=None,
            groq_primary_model="llama-3.3-70b-versatile",
            groq_current_model="meta-llama/llama-4-scout-17b-16e-instruct",
            groq_fallback_models=[
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "qwen/qwen3-32b",
            ],
        )

        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(
            fields["🤖 Groq 모델"],
            "시작: llama-3.3-70b-versatile\n"
            "현재: meta-llama/llama-4-scout-17b-16e-instruct\n"
            "fallback: meta-llama/llama-4-scout-17b-16e-instruct, qwen/qwen3-32b",
        )

    def test_omits_groq_model_field_when_model_tracking_is_empty(self):
        message = build_discord_run_message(
            team_slug="liverpool",
            briefing_type="morning",
            status="success",
            source_keys=["all"],
            payload=None,
            briefing_id=None,
        )

        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertNotIn("🤖 Groq 모델", fields)

    def test_discord_notifier_posts_json_payload(self):
        requests = []

        def fake_request(url, method, headers, body):
            requests.append(
                {
                    "url": url,
                    "method": method,
                    "headers": headers,
                    "body": json.loads(body.decode("utf-8")),
                }
            )
            return None

        notifier = DiscordNotifier(
            webhook_url="https://discord.com/api/webhooks/test",
            http_request=fake_request,
        )

        notifier.send({"content": "테스트 메시지"})

        self.assertEqual(requests[0]["url"], "https://discord.com/api/webhooks/test")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(requests[0]["headers"]["Content-Type"], "application/json")
        self.assertIn("SnippetFootballGeek", requests[0]["headers"]["User-Agent"])
        self.assertEqual(requests[0]["body"], {"content": "테스트 메시지"})

    def test_discord_notifier_wraps_http_errors(self):
        def fake_request(url, method, headers, body):
            raise HTTPError(url, 400, "Bad Request", {}, io.BytesIO(b'{"message":"Missing Access"}'))

        notifier = DiscordNotifier(
            webhook_url="https://discord.com/api/webhooks/test",
            http_request=fake_request,
        )

        with self.assertRaises(RuntimeError) as context:
            notifier.send({"content": "테스트 메시지"})

        self.assertIn("Discord webhook request failed", str(context.exception))
        self.assertIn("Missing Access", str(context.exception))


def _briefing_item(source_type: str) -> BriefingItem:
    return BriefingItem(
        section="top",
        headline_ko="리버풀 소식",
        body_ko="리버풀 관련 요약입니다.",
        category="team_news",
        category_label_ko="팀 소식",
        source_count=1,
        confidence_label="reported",
        source_urls=["https://example.com"],
        source_names=["Example"],
        source_type=source_type,
    )


if __name__ == "__main__":
    unittest.main()
