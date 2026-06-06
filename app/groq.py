"""Groq API 클라이언트와 기사 요약 프롬프트를 담당합니다.

Groq의 OpenAI 호환 chat completions endpoint를 감싸고, `Article`을 한국어
브리핑 요약으로 변환합니다. CLI에서 `--use-groq`로 활성화할 수 있으며,
비활성화하면 파이프라인은 로컬 템플릿 문구를 사용합니다.
"""

import json
import unicodedata
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.categories import normalize_category
from app.models import Article, SocialPost


DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
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
                "Return only JSON with keys headline_ko, body_ko, confidence_label, category. "
                "Use natural Korean with no awkward English verbs. "
                "Do not translate proper names for players, clubs, managers, journalists, stadiums, or publications. "
                "Always keep proper names in original Latin spelling exactly as they appear in the source text. "
                "Keep names like Federico Chiesa, Andoni Iraola, Arne Slot, Liverpool, Bournemouth, and Liverpool Echo in English. "
                "Never output broken mixed-script names or Chinese/Japanese characters for European football names. "
                "Do not use Hanja, Kanji, Hanzi, Kana, or any Chinese/Japanese characters in headline_ko or body_ko. "
                "Do not use Thai, Cyrillic, Greek, Arabic, Hebrew, Devanagari, or any other non-Korean and non-Latin script. "
                "Use a fan-friendly but careful tone. Do not present rumors as confirmed. "
                "Only use facts present in the provided title and body. Ignore clues from URLs. "
                "Do not add clubs, players, fees, injuries, quotes, or transfer status that are not in the title or body. "
                "Do not invent transfer fees, dates, injuries, quotes, or negotiation status that are not in the source text. "
                "If the article is only a report, write it as a report. "
                "confidence_label must be one of: official, reported, rumor, unconfirmed. "
                "category must be exactly one of: transfer, injury, match_result, match_preview, team_news, official, rumor, etc."
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
    result = {
        "headline_ko": str(summary["headline_ko"]),
        "body_ko": str(summary["body_ko"]),
        "confidence_label": _normalize_confidence_label(str(summary.get("confidence_label", "reported"))),
        "category": normalize_category(str(summary.get("category", "etc"))),
    }
    result = _restore_known_proper_names(result)
    if (
        _contains_disallowed_script(result["headline_ko"])
        or _contains_disallowed_script(result["body_ko"])
        or _is_mostly_untranslated_english(result["headline_ko"])
        or _is_mostly_untranslated_english(result["body_ko"])
    ):
        return _fallback_article_summary(article, result)
    return result


def summarize_social_post_with_groq(post: SocialPost, client: GroqClient) -> Dict[str, str]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Korean football editor writing concise Liverpool fan briefings from X posts. "
                "Return only JSON with keys headline_ko, body_ko, confidence_label, category. "
                "Clean retweets, mentions, emojis, tracking links, and line breaks into readable context. "
                "Do not quote the full tweet verbatim. Summarize what the post signals and who is claiming it. "
                "Keep player, club, manager, journalist, and publication names in original Latin spelling. "
                "Use natural Korean and avoid awkward translated names. "
                "Do not use Hanja, Kanji, Hanzi, Kana, Thai, Cyrillic, Greek, Arabic, Hebrew, or other non-Korean and non-Latin scripts. "
                "Never treat a repost, rumor, journalist claim, or report as official confirmation. "
                "If it is a retweet, explain it as the source sharing or amplifying another reporter's claim. "
                "Only use facts present in the provided post text and metadata. Ignore clues from URLs. "
                "confidence_label must be reporter_claim unless the post clearly says it is official. "
                "category must be exactly one of: transfer, injury, match_result, match_preview, team_news, official, rumor, etc."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source name: {post.source_name}\n"
                f"Author handle: {post.author_handle}\n"
                f"Post text: {post.text}\n\n"
                "Rewrite this as one short Liverpool briefing item in Korean."
            ),
        },
    ]
    summary = client.chat_json(messages)
    result = {
        "headline_ko": str(summary["headline_ko"]),
        "body_ko": str(summary["body_ko"]),
        "confidence_label": _normalize_social_confidence_label(str(summary.get("confidence_label", "reporter_claim"))),
        "category": normalize_category(str(summary.get("category", "etc"))),
    }
    result = _restore_known_proper_names(result)
    if _contains_disallowed_script(result["headline_ko"]) or _contains_disallowed_script(result["body_ko"]):
        return _fallback_social_post_summary(post, result)
    return result


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


def _normalize_social_confidence_label(value: str) -> str:
    allowed = {"official", "reporter_claim", "rumor", "unconfirmed"}
    return value if value in allowed else "reporter_claim"


def _contains_disallowed_script(value: str) -> bool:
    for character in value:
        if not unicodedata.category(character).startswith("L"):
            continue
        name = unicodedata.name(character, "")
        if name.startswith("LATIN") or name.startswith("HANGUL"):
            continue
        return True
    return False


def _restore_known_proper_names(summary: Dict[str, str]) -> Dict[str, str]:
    replacements = {
        "제임스 피어스": "James Pearce",
        "데이비드 온스테인": "David Ornstein",
        "데이비드 오른스틴": "David Ornstein",
        "리오 응구모하": "Rio Ngumoha",
        "커티스 존스": "Curtis Jones",
        "페데리코 키에사": "Federico Chiesa",
        "유르겐 클롭": "Jurgen Klopp",
        "위르겐 클롭": "Jurgen Klopp",
        "비르질 판 데이크": "Virgil van Dijk",
        "안도니 이라올라": "Andoni Iraola",
        "이라올라": "Andoni Iraola",
        "아르네 슬롯": "Arne Slot",
        "슬롯": "Arne Slot",
        "바이에른 뮌헨": "Bayern Munich",
        "레알 마드리드": "Real Madrid",
        "인터 밀란": "Inter Milan",
        "밀란": "Milan",
        "팔리스": "Crystal Palace",
        "레버쿠젠": "Leverkusen",
        "리버풀 에코": "Liverpool Echo",
    }
    restored = dict(summary)
    for key in ("headline_ko", "body_ko"):
        value = restored[key]
        for korean_name, latin_name in replacements.items():
            value = value.replace(korean_name, latin_name)
        restored[key] = value
    return restored


def _is_mostly_untranslated_english(value: str) -> bool:
    letters = [character for character in value if unicodedata.category(character).startswith("L")]
    if not letters:
        return False
    latin_count = sum(1 for character in letters if unicodedata.name(character, "").startswith("LATIN"))
    hangul_count = sum(1 for character in letters if unicodedata.name(character, "").startswith("HANGUL"))
    return latin_count >= 25 and hangul_count == 0


def _fallback_article_summary(article: Article, summary: Dict[str, str]) -> Dict[str, str]:
    subject = _article_fallback_subject(article)
    return {
        "headline_ko": f"{subject} 관련 {article.source_name} 보도",
        "body_ko": (
            f"{article.source_name}의 영문 원문을 바탕으로 추가 확인이 필요합니다. "
            "원문 확인이 필요한 리버풀 관련 보도입니다."
        ),
        "confidence_label": summary["confidence_label"],
        "category": summary["category"],
    }


def _article_fallback_subject(article: Article) -> str:
    known_subjects = [
        "Jurgen Klopp",
        "Real Madrid",
        "Federico Chiesa",
        "Curtis Jones",
        "Andoni Iraola",
        "Arne Slot",
        "Virgil van Dijk",
        "Rio Ngumoha",
        "Liverpool",
    ]
    for subject in known_subjects:
        if subject.lower() in article.title.lower() or subject.lower() in article.body.lower():
            return subject
    return "Liverpool"


def _fallback_social_post_summary(post: SocialPost, summary: Dict[str, str]) -> Dict[str, str]:
    return {
        "headline_ko": f"{post.source_name} 기자 신호",
        "body_ko": f"{post.source_name}가 X에서 리버풀 관련 소식을 공유했습니다. 원문 확인이 필요합니다.",
        "confidence_label": summary["confidence_label"],
        "category": summary["category"],
    }
