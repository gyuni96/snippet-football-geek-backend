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
        )

        self.assertIn("수집 완료", message["content"])
        self.assertEqual(message["embeds"][0]["title"], "Liverpool Briefing 수집 성공")
        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(fields["팀"], "liverpool")
        self.assertEqual(fields["브리핑"], "morning")
        self.assertEqual(fields["항목"], "총 2개 / 기사 1개 / X 1개")
        self.assertEqual(fields["저장"], "briefing-1")
        self.assertEqual(fields["소스"], "all")
        self.assertEqual(fields["GitHub Actions"], "https://github.com/example/repo/actions/runs/1")

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

        self.assertIn("실패", message["content"])
        fields = {field["name"]: field["value"] for field in message["embeds"][0]["fields"]}
        self.assertEqual(fields["항목"], "총 0개 / 기사 0개 / X 0개")
        self.assertEqual(fields["저장"], "저장 안 됨")
        self.assertEqual(fields["오류"], "Groq API failed")

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
