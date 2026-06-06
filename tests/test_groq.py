import json
import unittest
from urllib.error import HTTPError
from io import BytesIO

from app.groq import GroqAPIError, GroqClient, summarize_article_with_groq
from app.models import Article
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
            }
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["headline_ko"], "리버풀, 중원 보강 후보 주시")
        self.assertEqual(
            summary["body_ko"],
            "리버풀이 여름 이적시장을 앞두고 중원 보강 후보를 살펴보고 있다는 보도입니다.",
        )
        self.assertEqual(summary["confidence_label"], "reported")
        self.assertIn("Liverpool monitor midfield target", client.messages[1]["content"])
        self.assertIn("Do not translate proper names", client.messages[0]["content"])
        self.assertIn("Always keep proper names in original Latin spelling", client.messages[0]["content"])
        self.assertIn("Do not invent transfer fees", client.messages[0]["content"])
        self.assertIn("Only use facts present in the provided title and body", client.messages[0]["content"])

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
            }
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["confidence_label"], "reported")

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
