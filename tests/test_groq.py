import json
import unittest
from urllib.error import HTTPError
from io import BytesIO

from app.groq import (
    DEFAULT_GROQ_FALLBACK_MODELS,
    GroqAPIError,
    GroqClient,
    GroqModelRouter,
    GroqUsageGuard,
    summarize_article_with_groq,
    summarize_social_post_with_groq,
)
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
        self.assertIn("Bad headline", client.messages[0]["content"])
        self.assertIn("Good headline", client.messages[0]["content"])

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

    def test_summarize_article_with_groq_rejects_foreign_script_leaks(self):
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

        with self.assertRaises(GroqAPIError):
            summarize_article_with_groq(article, client)
        self.assertIn("Thai", client.message_calls[0][0]["content"])

    def test_summarize_article_with_groq_retries_with_compact_prompt(self):
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
            [
                {
                    "headline_ko": "Liverpool monitor midfield target",
                    "body_ko": "Liverpool Echo reports that Liverpool monitor a midfielder.",
                    "confidence_label": "reported",
                    "category": "transfer",
                },
                {
                    "headline_ko": "리버풀, 중원 보강 후보 주시",
                    "body_ko": "리버풀이 여름 이적시장을 앞두고 중원 보강 후보를 살펴보고 있다는 보도입니다.",
                    "confidence_label": "reported",
                    "category": "transfer",
                },
            ]
        )

        summary = summarize_article_with_groq(article, client)

        self.assertEqual(summary["headline_ko"], "리버풀, 중원 보강 후보 주시")
        self.assertEqual(len(client.message_calls), 2)
        self.assertIn("specific Korean headline", client.message_calls[1][0]["content"])

    def test_summarize_article_with_groq_does_not_retry_after_daily_token_limit(self):
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
            GroqAPIError(
                "Groq API request failed with status 429: Rate limit reached on tokens per day (TPD). "
                "Type: tokens Code: rate_limit_exceeded"
            )
        )

        with self.assertRaises(GroqAPIError):
            summarize_article_with_groq(article, client)

        self.assertEqual(len(client.message_calls), 1)

    def test_summarize_article_with_groq_truncates_long_body_before_request(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="article-1",
            canonical_url="https://example.com/story",
            title="Liverpool monitor midfield target",
            body="a" * 5000,
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

        summarize_article_with_groq(article, client)

        self.assertLess(len(client.messages[1]["content"]), 2200)
        self.assertNotIn("a" * 3000, client.messages[1]["content"])

    def test_summarize_article_with_groq_rejects_mostly_english_summary(self):
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

        with self.assertRaises(GroqAPIError):
            summarize_article_with_groq(article, client)

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
        self.assertIn("Do not quote the full tweet", client.messages[0]["content"])
        self.assertIn("Return valid JSON only", client.messages[0]["content"])
        self.assertIn("Never use generic headlines", client.messages[0]["content"])
        self.assertIn("weak social signal", client.messages[0]["content"])
        self.assertIn("Bad body", client.messages[0]["content"])
        self.assertIn("Good body", client.messages[0]["content"])
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
                "body_ko": "제임스 피어스가 데이비드 오르니스타인의 보도를 공유하며 리오 응구모하 관련 흐름을 전했습니다. 피에데리코 키에사와 파브리치오 로마노, 슬롯과 이라올라, 팔리스, 레버쿠젠도 언급됐습니다.",
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
        self.assertIn("Federico Chiesa", summary["body_ko"])
        self.assertIn("Fabrizio Romano", summary["body_ko"])
        self.assertIn("Arne Slot", summary["body_ko"])
        self.assertIn("Andoni Iraola", summary["body_ko"])
        self.assertIn("Crystal Palace", summary["body_ko"])
        self.assertIn("Leverkusen", summary["body_ko"])

    def test_summarize_social_post_with_groq_rejects_generic_summary(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="post-1",
            author_handle="LFCTransferRoom",
            text="🚨 Federico Chiesa opens possibility to Liverpool exit.",
            url="https://x.com/LFCTransferRoom/status/post-1",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "LFCTransferRoom 기자 신호",
                "body_ko": "LFCTransferRoom가 X에서 리버풀 관련 소식을 공유했습니다. 원문 확인이 필요합니다.",
                "confidence_label": "reporter_claim",
                "category": "transfer",
            }
        )

        with self.assertRaises(GroqAPIError):
            summarize_social_post_with_groq(post, client)

    def test_summarize_social_post_with_groq_retries_with_compact_prompt(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="post-1",
            author_handle="LFCTransferRoom",
            text="🚨 Federico Chiesa opens possibility to Liverpool exit.",
            url="https://x.com/LFCTransferRoom/status/post-1",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            [
                {
                    "headline_ko": "Federico Chiesa 관련 X 소식",
                    "body_ko": "LFCTransferRoom가 X에서 Federico Chiesa 관련 리버풀 소식을 전했습니다.",
                    "confidence_label": "reporter_claim",
                    "category": "transfer",
                },
                {
                    "headline_ko": "Federico Chiesa, 리버풀 이탈 가능성 언급",
                    "body_ko": "LFCTransferRoom은 Federico Chiesa가 리버풀을 떠날 가능성을 열어뒀다고 전했습니다.",
                    "confidence_label": "reporter_claim",
                    "category": "transfer",
                },
            ]
        )

        summary = summarize_social_post_with_groq(post, client)

        self.assertEqual(summary["headline_ko"], "Federico Chiesa, 리버풀 이탈 가능성 언급")
        self.assertEqual(len(client.message_calls), 2)
        self.assertIn("Do not use generic headlines", client.message_calls[1][0]["content"])

    def test_summarize_social_post_with_groq_marks_emoji_only_post_as_weak_signal(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="post-1",
            author_handle="LFCTransferRoom",
            text="😐",
            url="https://x.com/LFCTransferRoom/status/post-1",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )
        client = FakeGroqClient(
            {
                "headline_ko": "새 소식 없음",
                "body_ko": "LFCTransferRoom이 새 소식을 공유하지 않음",
                "confidence_label": "reporter_claim",
                "category": "etc",
            }
        )

        with self.assertRaises(GroqAPIError):
            summarize_social_post_with_groq(post, client)

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
        self.assertNotIn("response_format", captured["body"])

    def test_groq_client_parses_json_object_from_wrapped_text(self):
        def fake_http_post(url, headers, body):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Here is JSON:\n"
                                '{"headline_ko":"헤드라인","body_ko":"본문","confidence_label":"reported","category":"team_news"}'
                            )
                        }
                    }
                ]
            }

        client = GroqClient(api_key="test-key", model="test-model", http_post=fake_http_post)
        content = client.chat_json([{"role": "user", "content": "hello"}])

        self.assertEqual(content["headline_ko"], "헤드라인")

    def test_groq_client_waits_before_request_when_rate_limited(self):
        calls = []

        class FakeRateLimiter:
            def wait(self):
                calls.append("wait")

        def fake_http_post(url, headers, body):
            calls.append("post")
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

        client = GroqClient(
            api_key="test-key",
            model="test-model",
            http_post=fake_http_post,
            rate_limiter=FakeRateLimiter(),
        )
        client.chat_json([{"role": "user", "content": "hello"}])

        self.assertEqual(calls, ["wait", "post"])

    def test_groq_client_stops_before_http_when_max_requests_reached(self):
        calls = []

        def fake_http_post(url, headers, body):
            calls.append("post")
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

        guard = GroqUsageGuard(max_requests=1)
        client = GroqClient(api_key="test-key", model="test-model", http_post=fake_http_post, usage_guard=guard)

        client.chat_json([{"role": "user", "content": "first"}])
        with self.assertRaises(GroqAPIError) as context:
            client.chat_json([{"role": "user", "content": "second"}])

        self.assertEqual(calls, ["post"])
        self.assertIn("maximum Groq request budget", str(context.exception))

    def test_groq_client_marks_daily_token_limit_and_blocks_follow_up_requests(self):
        calls = []

        def fake_http_post(url, headers, body):
            calls.append("post")
            raise HTTPError(
                url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=BytesIO(
                    b'{"error":{"message":"Rate limit reached on tokens per day (TPD). Type: tokens Code: rate_limit_exceeded"}}'
                ),
            )

        guard = GroqUsageGuard(max_requests=10)
        client = GroqClient(api_key="test-key", model="test-model", http_post=fake_http_post, usage_guard=guard)

        with self.assertRaises(GroqAPIError):
            client.chat_json([{"role": "user", "content": "first"}])
        with self.assertRaises(GroqAPIError) as context:
            client.chat_json([{"role": "user", "content": "second"}])

        self.assertEqual(calls, ["post"])
        self.assertIn("daily token limit", str(context.exception))

    def test_groq_client_switches_to_fallback_model_after_daily_token_limit(self):
        requested_models = []
        switch_messages = []

        def fake_http_post(url, headers, body):
            requested_models.append(body["model"])
            if body["model"] == "primary-model":
                raise HTTPError(
                    url,
                    429,
                    "Too Many Requests",
                    hdrs=None,
                    fp=BytesIO(
                        b'{"error":{"message":"Rate limit reached for model `primary-model` on tokens per day (TPD). Type: tokens Code: rate_limit_exceeded"}}'
                    ),
                )
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

        router = GroqModelRouter(
            primary_model="primary-model",
            fallback_models=["fallback-model"],
            on_switch=switch_messages.append,
        )
        client = GroqClient(
            api_key="test-key",
            model_router=router,
            http_post=fake_http_post,
            usage_guard=GroqUsageGuard(max_requests=10),
        )

        content = client.chat_json([{"role": "user", "content": "hello"}])
        client.chat_json([{"role": "user", "content": "again"}])

        self.assertEqual(content["headline_ko"], "헤드라인")
        self.assertEqual(requested_models, ["primary-model", "fallback-model", "fallback-model"])
        self.assertEqual(router.current_model, "fallback-model")
        self.assertEqual(
            switch_messages,
            ["Groq model fallback: primary-model -> fallback-model (daily token limit reached)."],
        )

    def test_default_groq_fallback_models_exclude_8b_test_model(self):
        self.assertEqual(
            DEFAULT_GROQ_FALLBACK_MODELS,
            [
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "qwen/qwen3-32b",
            ],
        )
        self.assertNotIn("llama-3.1-8b-instant", DEFAULT_GROQ_FALLBACK_MODELS)

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
        self.responses = response if isinstance(response, list) else [response]
        self.messages = []
        self.message_calls = []

    def chat_json(self, messages):
        self.messages = messages
        self.message_calls.append(messages)
        response = self.responses[len(self.message_calls) - 1] if len(self.message_calls) <= len(self.responses) else self.responses[-1]
        if isinstance(response, Exception):
            raise response
        return response


if __name__ == "__main__":
    unittest.main()
