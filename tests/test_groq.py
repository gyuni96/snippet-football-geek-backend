import json
import unittest
from urllib.error import HTTPError
from io import BytesIO

from app.groq import GroqAPIError, GroqClient, summarize_article_with_groq, summarize_social_post_with_groq
from app.models import Article, SocialPost
from datetime import datetime, timezone


class GroqTest(unittest.TestCase):
    def test_summarize_article_with_groq_uses_json_response(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/story",
            title="Liverpool monitor midfield target",
            body="Liverpool are watching a midfielder before the summer transfer window.",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "리버풀, 중원 보강 후보 주시",
                "body_ko": "리버풀이 여름 이적시장을 앞두고 중원 보강 후보를 살펴보고 있다는 보도입니다.",
                "confidence_label": "reported",
                "category": "transfer",
            }
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["headline_ko"], "리버풀, 중원 보강 후보 주시")
        self.assertEqual(
            summary["body_ko"],
            "리버풀이 여름 이적시장을 앞두고 중원 보강 후보를 살펴보고 있다는 보도입니다.",
        )
        self.assertEqual(summary["confidence_label"], "reported")
        self.assertEqual(summary["category"], "transfer")
        self.assertIn("Liverpool monitor midfield target", client.messages[1]["content"])
        self.assertIn("category", client.messages[0]["content"])
        self.assertIn("Do not translate proper names", client.messages[0]["content"])
        self.assertIn("Always keep proper names in original Latin spelling", client.messages[0]["content"])
        self.assertIn("Do not invent transfer fees", client.messages[0]["content"])
        self.assertIn("Only use facts present in the provided title and body", client.messages[0]["content"])
        self.assertIn("Do not use Hanja, Kanji, Hanzi, Kana", client.messages[0]["content"])

    def test_summarize_article_with_groq_normalizes_unknown_confidence_label(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/story",
            title="Liverpool monitor midfield target",
            body="Liverpool are watching a midfielder before the summer transfer window.",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "리버풀, 중원 보강 후보 주시",
                "body_ko": "리버풀이 여름 이적시장을 앞두고 중원 보강 후보를 살펴보고 있다는 보도입니다.",
                "confidence_label": "중",
                "category": "unknown",
            }
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["confidence_label"], "reported")
        self.assertEqual(summary["category"], "etc")

    def test_summarize_article_with_groq_falls_back_when_foreign_script_leaks(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/story",
            title="Jurgen Klopp responds to Real Madrid links",
            body="Jurgen Klopp was asked again about links with Real Madrid.",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "유르겐 คล롭의 레알 마드리드 링크",
                "body_ko": "유르겐 คล롭이 레알 마드리드와의 링크에 대해 답했습니다.",
                "confidence_label": "reported",
                "category": "rumor",
            }
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["headline_ko"], "Jurgen Klopp 관련 Liverpool Echo 보도")
        self.assertIn("원문 확인이 필요한 리버풀 관련 보도입니다", summary["body_ko"])
        self.assertEqual(summary["confidence_label"], "reported")
        self.assertEqual(summary["category"], "rumor")
        self.assertIn("Thai", client.messages[0]["content"])

    def test_summarize_article_with_groq_falls_back_when_summary_is_mostly_english(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/story",
            title="Jurgen Klopp responds to Real Madrid links",
            body="Jurgen Klopp was asked again about links with Real Madrid.",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "Jurgen Klopp comments about coaching return speak volumes",
                "body_ko": "Liverpool Echo reports that Jurgen Klopp has had to field reports linking him to Real Madrid.",
                "confidence_label": "reported",
                "category": "rumor",
            }
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["headline_ko"], "Jurgen Klopp 관련 Liverpool Echo 보도")
        self.assertIn("영문 원문을 바탕으로 추가 확인이 필요합니다", summary["body_ko"])

    def test_summarize_social_post_with_groq_uses_editorial_prompt(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="James Pearce",
            external_post_id="post-1",
            author_handle="JamesPearceLFC",
            text="RT @David_Ornstein: Bayern Munich exploring move to sign Rio Ngumoha.",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "Bayern, Rio Ngumoha 관심 보도 확산",
                "body_ko": "James Pearce가 David Ornstein의 보도를 공유하며 Bayern Munich의 Rio Ngumoha 관심을 전했습니다.",
                "confidence_label": "reporter_claim",
                "category": "transfer",
            }
        )

        summary = summarize_social_post_with_groq(post, client)

        self.assertEqual(summary["headline_ko"], "Bayern, Rio Ngumoha 관심 보도 확산")
        self.assertEqual(summary["confidence_label"], "reporter_claim")
        self.assertEqual(summary["category"], "transfer")
        self.assertIn("Clean retweets", client.messages[0]["content"])
        self.assertIn("Do not quote the full tweet verbatim", client.messages[0]["content"])
        self.assertIn("RT @David_Ornstein", client.messages[1]["content"])

    def test_summarize_social_post_with_groq_restores_known_proper_names(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="James Pearce",
            external_post_id="post-1",
            author_handle="JamesPearceLFC",
            text="James Pearce shared David Ornstein's report about Rio Ngumoha.",
            url="https://x.com/JamesPearceLFC/status/post-1",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "제임스 피어스, 리오 응구모하 관련 보도 공유",
                "body_ko": "제임스 피어스가 데이비드 온스테인의 보도를 공유하며 리오 응구모하 관련 흐름을 전했습니다. 슬롯과 이라올라, 팔리스, 레버쿠젠도 언급됐습니다.",
                "confidence_label": "reporter_claim",
                "category": "transfer",
            }
        )

        summary = summarize_social_post_with_groq(post, client)

        self.assertIn("James Pearce", summary["headline_ko"])
        self.assertIn("Rio Ngumoha", summary["headline_ko"])
        self.assertIn("James Pearce", summary["body_ko"])
        self.assertIn("David Ornstein", summary["body_ko"])
        self.assertIn("Rio Ngumoha", summary["body_ko"])
        self.assertIn("Arne Slot", summary["body_ko"])
        self.assertIn("Andoni Iraola", summary["body_ko"])
        self.assertIn("Crystal Palace", summary["body_ko"])
        self.assertIn("Leverkusen", summary["body_ko"])

    def test_groq_client_builds_chat_completion_request(self):
        captured = {}

        def fake_http_post(url, headers, body):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = body
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "headline_ko": "헤드라인",
                                    "body_ko": "본문",
                                    "confidence_label": "reported",
                                    "category": "team_news",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        client = GroqClient(api_key="test-key", model="test-model", http_post=fake_http_post)
        content = client.chat_json([{"role": "user", "content": "hello"}])

        self.assertEqual(content["headline_ko"], "헤드라인")
        self.assertEqual(captured["url"], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(captured["headers"]["User-Agent"], "SnippetFootballGeekBot/0.1")
        self.assertEqual(captured["body"]["model"], "test-model")

    def test_groq_client_converts_http_error_to_safe_error_message(self):
        def fake_http_post(url, headers, body):
            raise HTTPError(
                url,
                403,
                "Forbidden",
                hdrs=None,
                fp=BytesIO(b'{"error":{"message":"model restricted"}}'),
            )

        client = GroqClient(api_key="test-key", model="test-model", http_post=fake_http_post)

        with self.assertRaises(GroqAPIError) as context:
            client.chat_json([{"role": "user", "content": "hello"}])

        self.assertIn("Groq API request failed with status 403", str(context.exception))
        self.assertIn("model restricted", str(context.exception))


class FakeGroqClient:
    def __init__(self, response):
        self.response = response
        self.messages = []

    def chat_json(self, messages):
        self.messages = messages
        return self.response


if __name__ == "__main__":
    unittest.main()
