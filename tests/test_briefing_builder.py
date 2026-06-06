from datetime import datetime, timezone
import unittest

from app.briefing_builder import build_briefing_payload
from app.models import Article, SocialPost


class BriefingBuilderTest(unittest.TestCase):
    def test_builds_morning_briefing_from_article_and_social_post(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/liverpool-midfielder",
            title="Liverpool monitor midfield target",
            body="Liverpool are watching a midfielder ahead of the summer window.",
            published_at=published_at,
            author="Reporter",
        )
        social_post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="James Pearce",
            external_post_id="post-1",
            author_handle="JamesPearceLFC",
            text="Liverpool are not planning to sell the player this summer.",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at=published_at,
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[article],
            social_posts=[social_post],
            published_at=published_at,
        )

        self.assertEqual(payload.team_slug, "liverpool")
        self.assertEqual(payload.briefing_type, "morning")
        self.assertEqual(payload.title, "리버풀 아침 브리핑")
        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 2건입니다.")
        self.assertEqual(len(payload.items), 2)
        self.assertEqual(payload.items[0].section, "top_stories")
        self.assertEqual(payload.items[0].confidence_label, "reported")
        self.assertEqual(payload.items[1].section, "reporter_signals")
        self.assertEqual(payload.items[1].confidence_label, "reporter_claim")

    def test_builds_article_item_with_groq_summarizer_when_provided(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/liverpool-midfielder",
            title="Liverpool monitor midfield target",
            body="Liverpool are watching a midfielder ahead of the summer window.",
            published_at=published_at,
            author="Reporter",
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[article],
            social_posts=[],
            published_at=published_at,
            article_summarizer=lambda item: {
                "headline_ko": "리버풀, 중원 후보 주시",
                "body_ko": "여름 이적시장을 앞두고 체크할 만한 흐름입니다.",
                "confidence_label": "reported",
            },
        )

        self.assertEqual(payload.items[0].headline_ko, "리버풀, 중원 후보 주시")
        self.assertEqual(payload.items[0].body_ko, "여름 이적시장을 앞두고 체크할 만한 흐름입니다.")


if __name__ == "__main__":
    unittest.main()
