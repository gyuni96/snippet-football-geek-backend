"""Groq API client and article summarization prompts.

This module wraps Groq's OpenAI-compatible chat completions endpoint and turns
an `Article` into a Korean briefing summary. The CLI can enable this with
`--use-groq`; otherwise the pipeline keeps using local template text.
"""

import json
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.models import Article


DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


HttpPost = Callable[[str, Dict[str, str], Dict[str, Any]], Dict[str, Any]]


class GroqAPIError(RuntimeError):
    pass


class GroqClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GROQ_MODEL,
        http_post: Optional[HttpPost] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.http_post = http_post or _http_post_json

    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        try:
            response = self.http_post(
                GROQ_CHAT_URL,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "SnippetFootballGeekBot/0.1",
                },
                {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
        except HTTPError as error:
            raise GroqAPIError(_format_http_error(error)) from error
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)


def summarize_article_with_groq(article: Article, client: GroqClient) -> Dict[str, str]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Korean football editor writing for Liverpool fans. "
                "Return only JSON with keys headline_ko, body_ko, confidence_label. "
                "Use natural Korean with no awkward English verbs. Keep player, club, and journalist names as proper nouns. "
                "Use a fan-friendly but careful tone. Do not present rumors as confirmed. "
                "confidence_label must be one of: official, reported, rumor, unconfirmed."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source: {article.source_name}\n"
                f"Title: {article.title}\n"
                f"Body: {article.body}\n\n"
                "Summarize this as one short Liverpool briefing item in Korean."
            ),
        },
    ]
    summary = client.chat_json(messages)
    return {
        "headline_ko": str(summary["headline_ko"]),
        "body_ko": str(summary["body_ko"]),
        "confidence_label": _normalize_confidence_label(str(summary.get("confidence_label", "reported"))),
    }


def _http_post_json(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _format_http_error(error: HTTPError) -> str:
    body = error.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
        message = parsed.get("error", {}).get("message") or body
    except json.JSONDecodeError:
        message = body
    return f"Groq API request failed with status {error.code}: {message}"


def _normalize_confidence_label(value: str) -> str:
    allowed = {"official", "reported", "rumor", "unconfirmed"}
    return value if value in allowed else "reported"
