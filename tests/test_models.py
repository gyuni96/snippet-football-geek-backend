from datetime import datetime, timezone
import unittest

from app.models import ArticleBriefingItem, BriefingItem, BriefingPayload, TweetBriefingItem


class BriefingPayloadTest(unittest.TestCase):
    def test_briefing_payload_to_dict_returns_json_ready_shape(self):
        published_at = datetime(2026, 6, 6, 7, 30, tzinfo=timezone.utc)
        payload = BriefingPayload(
            team_slug="liverpool",
            briefing_type="morning",
            title="리버풀 아침 브리핑",
            summary_ko="출근길에 확인할 리버풀 핵심 소식입니다.",
            published_at=published_at,
            items=[
                BriefingItem(
                    section="top_stories",
                    headline_ko="중원 보강 후보 재점화",
                    body_ko="아직 협상 단계는 아니지만 체크할 만한 흐름입니다.",
                    source_count=2,
                    confidence_label="reported",
                    source_urls=["https://example.com/news"],
                    source_names=["Liverpool Echo"],
                    source_type="article",
                    category="transfer",
                    category_label_ko="이적",
                    published_at=published_at,
                    event_at=datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc),
                )
            ],
            article_items=[
                ArticleBriefingItem(
                    section="top_stories",
                    headline_ko="중원 보강 후보 재점화",
                    body_ko="아직 협상 단계는 아니지만 체크할 만한 흐름입니다.",
                    category="transfer",
                    category_label_ko="이적",
                    source_count=2,
                    confidence_label="reported",
                    source_urls=["https://example.com/news"],
                    source_names=["Liverpool Echo"],
                    published_at=published_at,
                    event_at=datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc),
                    llm_provider="groq",
                    llm_model="meta-llama/llama-4-scout-17b-16e-instruct",
                )
            ],
            tweet_items=[
                TweetBriefingItem(
                    headline_ko="James Pearce, 이적 흐름 언급",
                    body_ko="James Pearce는 Liverpool의 이적 시장 흐름을 전했습니다.",
                    translated_text_ko="Liverpool의 이적 시장 흐름에 대한 게시물입니다.",
                    original_text="Liverpool transfer update.",
                    category="transfer",
                    category_label_ko="이적",
                    confidence_label="reporter_claim",
                    tweet_id="post-1",
                    author_handle="JamesPearceLFC",
                    author_name="James Pearce",
                    tweet_url="https://x.com/JamesPearceLFC/status/post-1",
                    published_at=published_at,
                    llm_provider="groq",
                    llm_model="meta-llama/llama-4-scout-17b-16e-instruct",
                )
            ],
        )

        self.assertEqual(
            payload.to_dict(),
            {
                "team_slug": "liverpool",
                "briefing_type": "morning",
                "title": "리버풀 아침 브리핑",
                "summary_ko": "출근길에 확인할 리버풀 핵심 소식입니다.",
                "published_at": "2026-06-06T07:30:00+00:00",
                "items": [
                    {
                        "section": "top_stories",
                        "headline_ko": "중원 보강 후보 재점화",
                        "body_ko": "아직 협상 단계는 아니지만 체크할 만한 흐름입니다.",
                        "source_count": 2,
                        "confidence_label": "reported",
                        "source_urls": ["https://example.com/news"],
                        "source_names": ["Liverpool Echo"],
                        "source_type": "article",
                        "category": "transfer",
                        "category_label_ko": "이적",
                        "published_at": "2026-06-06T07:30:00+00:00",
                        "event_at": "2026-08-02T20:00:00+00:00",
                    }
                ],
                "article_items": [
                    {
                        "section": "top_stories",
                        "headline_ko": "중원 보강 후보 재점화",
                        "body_ko": "아직 협상 단계는 아니지만 체크할 만한 흐름입니다.",
                        "category": "transfer",
                        "category_label_ko": "이적",
                        "source_count": 2,
                        "confidence_label": "reported",
                        "source_urls": ["https://example.com/news"],
                        "source_names": ["Liverpool Echo"],
                        "published_at": "2026-06-06T07:30:00+00:00",
                        "event_at": "2026-08-02T20:00:00+00:00",
                        "llm_provider": "groq",
                        "llm_model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    }
                ],
                "tweet_items": [
                    {
                        "headline_ko": "James Pearce, 이적 흐름 언급",
                        "body_ko": "James Pearce는 Liverpool의 이적 시장 흐름을 전했습니다.",
                        "translated_text_ko": "Liverpool의 이적 시장 흐름에 대한 게시물입니다.",
                        "original_text": "Liverpool transfer update.",
                        "category": "transfer",
                        "category_label_ko": "이적",
                        "confidence_label": "reporter_claim",
                        "tweet_id": "post-1",
                        "author_handle": "JamesPearceLFC",
                        "author_name": "James Pearce",
                        "tweet_url": "https://x.com/JamesPearceLFC/status/post-1",
                        "published_at": "2026-06-06T07:30:00+00:00",
                        "llm_provider": "groq",
                        "llm_model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    }
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
