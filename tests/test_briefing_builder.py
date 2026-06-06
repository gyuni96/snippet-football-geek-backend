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
        self.assertEqual(payload.items[0].source_names, ["Liverpool Echo"])
        self.assertEqual(payload.items[0].source_type, "article")
        self.assertEqual(payload.items[0].category, "transfer")
        self.assertEqual(payload.items[0].category_label_ko, "이적")
        self.assertEqual(payload.items[1].section, "reporter_signals")
        self.assertEqual(payload.items[1].confidence_label, "reporter_claim")
        self.assertEqual(payload.items[1].source_names, ["James Pearce"])
        self.assertEqual(payload.items[1].source_type, "social_post")
        self.assertEqual(payload.items[1].category, "transfer")
        self.assertEqual(payload.items[1].category_label_ko, "이적")

    def test_builds_social_post_item_with_summarizer_when_provided(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        social_post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="James Pearce",
            external_post_id="post-1",
            author_handle="JamesPearceLFC",
            text="RT @David_Ornstein: Bayern Munich exploring move to sign Rio Ngumoha.",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at=published_at,
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[],
            social_posts=[social_post],
            published_at=published_at,
            social_post_summarizer=lambda post: {
                "headline_ko": "Bayern, Rio Ngumoha 관심 보도 확산",
                "body_ko": "James Pearce가 David Ornstein의 보도를 공유하며 Bayern Munich의 Rio Ngumoha 관심을 전했습니다.",
                "confidence_label": "reporter_claim",
                "category": "transfer",
            },
        )

        self.assertEqual(payload.items[0].headline_ko, "Bayern, Rio Ngumoha 관심 보도 확산")
        self.assertIn("David Ornstein", payload.items[0].body_ko)
        self.assertEqual(payload.items[0].confidence_label, "reporter_claim")
        self.assertEqual(payload.items[0].category, "transfer")

    def test_skips_social_post_when_summarizer_fails(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
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
            articles=[],
            social_posts=[social_post],
            published_at=published_at,
            social_post_summarizer=lambda item: (_ for _ in ()).throw(RuntimeError("Groq failed")),
        )

        self.assertEqual(payload.items, [])

    def test_skips_low_signal_social_post(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        social_post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="Anfield Sector",
            external_post_id="post-1",
            author_handle="AnfieldSector",
            text="via: https://t.co/example",
            url="https://x.com/AnfieldSector/status/post-1",
            published_at=published_at,
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[],
            social_posts=[social_post],
            published_at=published_at,
        )

        self.assertEqual(payload.items, [])
        self.assertEqual(payload.summary_ko, "출근길에 확인할 리버풀 핵심 소식 0건입니다.")

    def test_skips_social_post_fallback_without_known_subject(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        social_post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="post-1",
            author_handle="LFCTransferRoom",
            text="Some clubs are watching the situation closely.",
            url="https://x.com/LFCTransferRoom/status/post-1",
            published_at=published_at,
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[],
            social_posts=[social_post],
            published_at=published_at,
            social_post_summarizer=lambda item: (_ for _ in ()).throw(RuntimeError("Groq failed")),
        )

        self.assertEqual(payload.items, [])

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
                "category": "transfer",
            },
        )

        self.assertEqual(payload.items[0].headline_ko, "리버풀, 중원 후보 주시")
        self.assertEqual(payload.items[0].body_ko, "여름 이적시장을 앞두고 체크할 만한 흐름입니다.")
        self.assertEqual(payload.items[0].category, "transfer")
        self.assertEqual(payload.items[0].category_label_ko, "이적")

    def test_skips_article_when_summarizer_fails(self):
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
            article_summarizer=lambda item: (_ for _ in ()).throw(RuntimeError("Groq failed")),
        )

        self.assertEqual(payload.items, [])

    def test_skips_article_when_summary_quality_is_too_poor(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        article = Article(
            team_slug="liverpool",
            source_name="This Is Anfield",
            external_id="article-1",
            canonical_url="https://example.com/van-dijk",
            title="Virgil van Dijk explains Anfield moment",
            body="Virgil van Dijk explained why he sat alone on the Anfield pitch.",
            published_at=published_at,
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[article],
            social_posts=[],
            published_at=published_at,
            article_summarizer=lambda item: {
                "headline_ko": "비르길 판 디jk, 안필드에서 혼자 울었다는 이유는?",
                "body_ko": "비르길 판 디jk는 안필드에서 혼자 울었다는 이유를 설명했다.",
                "confidence_label": "reported",
                "category": "team_news",
            },
        )

        self.assertEqual(payload.items, [])

    def test_skips_social_post_when_summary_is_generic(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        social_post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="post-1",
            author_handle="LFCTransferRoom",
            text="Liverpool could have a double profit opportunity.",
            url="https://x.com/LFCTransferRoom/status/post-1",
            published_at=published_at,
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[],
            social_posts=[social_post],
            published_at=published_at,
            social_post_summarizer=lambda item: {
                "headline_ko": "리버풀, 이중 수익 기회",
                "body_ko": "LFCTransferRoom이 공유했습니다.",
                "confidence_label": "reporter_claim",
                "category": "transfer",
            },
        )

        self.assertEqual(payload.items, [])

    def test_builds_article_item_with_multiple_sources(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool FC Official Website",
            external_id="article-1",
            canonical_url="https://www.liverpoolfc.com/news/iraola",
            title="Liverpool appoint Andoni Iraola",
            body="Liverpool have appointed Andoni Iraola.",
            published_at=published_at,
            source_urls=[
                "https://www.liverpoolfc.com/news/iraola",
                "https://www.skysports.com/football/news/iraola-liverpool",
            ],
            source_names=["Liverpool FC Official Website", "Sky Sports - Liverpool"],
        )

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="morning",
            articles=[article],
            social_posts=[],
            published_at=published_at,
        )

        self.assertEqual(payload.items[0].source_count, 2)
        self.assertEqual(
            payload.items[0].source_names,
            ["Liverpool FC Official Website", "Sky Sports - Liverpool"],
        )
        self.assertEqual(
            payload.items[0].source_urls,
            [
                "https://www.liverpoolfc.com/news/iraola",
                "https://www.skysports.com/football/news/iraola-liverpool",
            ],
        )

    def test_builds_afternoon_briefing_title(self):
        published_at = datetime(2026, 6, 6, 16, 0, tzinfo=timezone.utc)

        payload = build_briefing_payload(
            team_slug="liverpool",
            briefing_type="afternoon",
            articles=[],
            social_posts=[],
            published_at=published_at,
        )

        self.assertEqual(payload.title, "리버풀 오후 브리핑")


if __name__ == "__main__":
    unittest.main()
