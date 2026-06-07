"""Groq API 클라이언트와 기사 요약 프롬프트를 담당합니다.

Groq의 OpenAI 호환 chat completions endpoint를 감싸고, `Article`을 한국어
브리핑 요약으로 변환합니다. CLI에서 `--use-groq`로 활성화할 수 있으며,
비활성화하면 파이프라인은 로컬 템플릿 문구를 사용합니다.
"""

import json
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.categories import normalize_category
from app.models import Article, SocialPost


DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GROQ_FALLBACK_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
]
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
ARTICLE_BODY_PROMPT_LIMIT = 1200
SOCIAL_POST_PROMPT_LIMIT = 800
TEST_ONLY_GROQ_MODELS = {"llama-3.1-8b-instant"}
BRIEFING_STYLE_GUIDE = (
    "Style guide: write like a concise Korean Liverpool commute briefing. "
    "headline_ko must be 18-36 Korean-friendly characters when possible and name the concrete subject. "
    "body_ko must be one natural Korean sentence around 45-90 characters. "
    "Avoid hype, clickbait, and repeated source-only phrasing. "
    "Bad headline: 리버풀 관련 이적 소식. Good headline: Liverpool, Rio Ngumoha 매각 불가 방침. "
    "Bad body: LFCTransferRoom이 관련 소식을 공유했습니다. "
    "Good body: LFCTransferRoom은 Bayern Munich 관심에도 Liverpool이 Rio Ngumoha를 팔지 않을 방침이라고 전했다. "
)


HttpPost = Callable[[str, Dict[str, str], Dict[str, Any]], Dict[str, Any]]


class GroqAPIError(RuntimeError):
    pass


class GroqRateLimiter:
    """Groq 요청 간격을 제한해 무료/저속 플랜에서 과도한 호출을 피합니다."""

    def __init__(self, requests_per_minute: int):
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive.")
        self.min_interval_seconds = 60 / requests_per_minute
        self.last_request_at = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_request_at
        wait_seconds = self.min_interval_seconds - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        self.last_request_at = time.monotonic()


class GroqUsageGuard:
    """실행 1회 안에서 Groq 요청량과 일일 토큰 한도 초과 상태를 관리합니다."""

    def __init__(self, max_requests: Optional[int] = None):
        if max_requests is not None and max_requests <= 0:
            raise ValueError("max_requests must be positive.")
        self.max_requests = max_requests
        self.request_count = 0
        self.daily_token_limit_reached = False

    def ensure_can_request(self) -> None:
        if self.daily_token_limit_reached:
            raise GroqAPIError("Groq daily token limit has been reached; skipping remaining Groq requests.")
        if self.max_requests is not None and self.request_count >= self.max_requests:
            raise GroqAPIError("Groq maximum Groq request budget reached; skipping remaining Groq requests.")

    def record_request(self) -> None:
        self.request_count += 1

    def mark_daily_token_limit_reached(self) -> None:
        self.daily_token_limit_reached = True


class GroqModelRouter:
    """Groq 모델 한도 초과 시 실행 중 사용할 다음 운영 모델을 선택합니다."""

    def __init__(
        self,
        primary_model: str,
        fallback_models: Optional[List[str]] = None,
        on_switch: Optional[Callable[[str], None]] = None,
    ):
        self.models = _dedupe_models([primary_model] + list(fallback_models or []))
        self.current_index = 0
        self.on_switch = on_switch

    @property
    def current_model(self) -> str:
        return self.models[self.current_index]

    def switch_after_daily_token_limit(self) -> bool:
        if self.current_index + 1 >= len(self.models):
            return False
        previous_model = self.current_model
        self.current_index += 1
        message = f"{previous_model} 일일 토큰 한도 초과로 {self.current_model} 모델로 전환했습니다."
        if self.on_switch is not None:
            self.on_switch(message)
        return True


class GroqClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GROQ_MODEL,
        fallback_models: Optional[List[str]] = None,
        model_router: Optional[GroqModelRouter] = None,
        http_post: Optional[HttpPost] = None,
        rate_limiter: Optional[GroqRateLimiter] = None,
        usage_guard: Optional[GroqUsageGuard] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.model_router = model_router or GroqModelRouter(model, fallback_models)
        self.http_post = http_post or _http_post_json
        self.rate_limiter = rate_limiter
        self.usage_guard = usage_guard

    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        while True:
            try:
                if self.usage_guard is not None:
                    self.usage_guard.ensure_can_request()
                if self.rate_limiter is not None:
                    self.rate_limiter.wait()
                if self.usage_guard is not None:
                    self.usage_guard.record_request()
                response = self.http_post(
                    GROQ_CHAT_URL,
                    {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "SnippetFootballGeekBot/0.1",
                    },
                    {
                        "model": self.model_router.current_model,
                        "messages": messages,
                        "temperature": 0.2,
                    },
                )
                break
            except HTTPError as error:
                message = _format_http_error(error)
                if _is_daily_token_limit_error(message) and self.model_router.switch_after_daily_token_limit():
                    continue
                if self.usage_guard is not None and _is_daily_token_limit_error(message):
                    self.usage_guard.mark_daily_token_limit_reached()
                raise GroqAPIError(message) from error
        content = response["choices"][0]["message"]["content"]
        return _parse_json_object(content)


def summarize_article_with_groq(article: Article, client: GroqClient) -> Dict[str, str]:
    message_sets = [
        _article_summary_messages(article),
        _article_retry_messages(article),
    ]
    last_error: Optional[Exception] = None
    for messages in message_sets:
        try:
            summary = client.chat_json(messages)
            result = {
                "headline_ko": str(summary["headline_ko"]),
                "body_ko": str(summary["body_ko"]),
                "confidence_label": _normalize_confidence_label(str(summary.get("confidence_label", "reported"))),
                "category": normalize_category(str(summary.get("category", "etc"))),
            }
            result = _restore_known_proper_names(result)
            _ensure_article_summary_quality(result)
            return result
        except (GroqAPIError, KeyError, TypeError) as error:
            if _is_groq_protection_error(error):
                raise
            last_error = error

    raise GroqAPIError("Groq article summary failed after retry.") from last_error


def _article_summary_messages(article: Article) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a Korean football editor writing for Liverpool fans. "
                f"{BRIEFING_STYLE_GUIDE}"
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
                f"Body: {_trim_prompt_text(article.body, ARTICLE_BODY_PROMPT_LIMIT)}\n\n"
                "Summarize this as one short Liverpool briefing item in Korean."
            ),
        },
    ]


def summarize_social_post_with_groq(post: SocialPost, client: GroqClient) -> Dict[str, str]:
    message_sets = [
        _social_post_summary_messages(post),
        _social_post_retry_messages(post),
    ]
    last_error: Optional[Exception] = None
    for messages in message_sets:
        try:
            summary = client.chat_json(messages)
            result = {
                "headline_ko": str(summary["headline_ko"]),
                "body_ko": str(summary["body_ko"]),
                "confidence_label": _normalize_social_confidence_label(str(summary.get("confidence_label", "reporter_claim"))),
                "category": normalize_category(str(summary.get("category", "etc"))),
            }
            result = _restore_known_proper_names(result)
            _ensure_social_post_summary_quality(result)
            return result
        except (GroqAPIError, KeyError, TypeError) as error:
            if _is_groq_protection_error(error):
                raise
            last_error = error

    raise GroqAPIError("Groq social post summary failed after retry.") from last_error


def _social_post_summary_messages(post: SocialPost) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a Korean football editor writing concise Liverpool fan briefings from X posts. "
                f"{BRIEFING_STYLE_GUIDE}"
                "Return valid JSON only, no markdown, no extra text. "
                "Schema: {\"headline_ko\":\"...\",\"body_ko\":\"...\",\"confidence_label\":\"reporter_claim\",\"category\":\"transfer\"}. "
                "headline_ko: concrete news/event headline, not a source label. Never use generic headlines like 기자 신호, 리버풀 관련 소식, 새 소식 없음, 원문 확인 필요. "
                "body_ko: one compact Korean sentence explaining who posted it and what was claimed or shared. "
                "Clean retweets, mentions, emojis, tracking links, and line breaks. Do not quote the full tweet. "
                "If the post is only an emoji, reaction, vague reply, or bare link, use category etc and describe it as a weak social signal. "
                "Keep proper names in Latin spelling: players, clubs, managers, journalists, publications. "
                "Use only facts from the post text and metadata. Ignore URL clues. Do not present claims as official confirmation. "
                "confidence_label must be one of: official, reporter_claim, rumor, unconfirmed. "
                "category must be one of: transfer, injury, match_result, match_preview, team_news, official, rumor, etc."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source name: {post.source_name}\n"
                f"Author handle: {post.author_handle}\n"
                f"Post text: {_trim_prompt_text(post.text, SOCIAL_POST_PROMPT_LIMIT)}\n\n"
                "Rewrite this as one short Liverpool briefing item in Korean."
            ),
        },
    ]


def _article_retry_messages(article: Article) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. Write natural Korean for Liverpool fans. "
                f"{BRIEFING_STYLE_GUIDE}"
                "Keys: headline_ko, body_ko, confidence_label, category. "
                "headline_ko must be a specific Korean headline, not '~관련 소식'. "
                "body_ko must summarize the actual news in one Korean sentence. "
                "Keep names such as Liverpool, Jurgen Klopp, Arne Slot, Andoni Iraola, Rio Ngumoha in Latin letters. "
                "Do not invent facts. Use only the supplied title/body. "
                "confidence_label: official, reported, rumor, unconfirmed. "
                "category: transfer, injury, match_result, match_preview, team_news, official, rumor, etc."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Title: {article.title}\n"
                f"Body: {_trim_prompt_text(article.body, ARTICLE_BODY_PROMPT_LIMIT)}\n\n"
                "Create one concise Korean briefing item."
            ),
        },
    ]


def _social_post_retry_messages(post: SocialPost) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. Write one concise Korean Liverpool briefing item from this X post. "
                f"{BRIEFING_STYLE_GUIDE}"
                "Keys: headline_ko, body_ko, confidence_label, category. "
                "Do not use generic headlines like '~관련 X 소식', '기자 신호', or '리버풀 관련 소식'. "
                "If the post has no concrete claim, set category to etc and write that it is a weak signal. "
                "Do not quote the full post. Keep proper names in Latin letters. "
                "confidence_label: official, reporter_claim, rumor, unconfirmed. "
                "category: transfer, injury, match_result, match_preview, team_news, official, rumor, etc."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source: {post.source_name} (@{post.author_handle})\n"
                f"Post: {_trim_prompt_text(post.text, SOCIAL_POST_PROMPT_LIMIT)}\n\n"
                "Create one Korean briefing item."
            ),
        },
    ]


def _http_post_json(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> Dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_json_object(content: str) -> Dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise GroqAPIError("Groq response was not valid JSON.")
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError as error:
            raise GroqAPIError("Groq response was not valid JSON.") from error
        if not isinstance(parsed, dict):
            raise GroqAPIError("Groq response JSON was not an object.")
        return parsed


def _dedupe_models(models: List[str]) -> List[str]:
    result = []
    seen = set()
    for index, model in enumerate(models):
        normalized = model.strip()
        if not normalized or normalized in seen:
            continue
        if index > 0 and normalized in TEST_ONLY_GROQ_MODELS:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _format_http_error(error: HTTPError) -> str:
    body = error.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
        message = parsed.get("error", {}).get("message") or body
    except json.JSONDecodeError:
        message = body
    return f"Groq API request failed with status {error.code}: {message}"


def _trim_prompt_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def _is_groq_protection_error(error: Exception) -> bool:
    message = str(error)
    return (
        _is_daily_token_limit_error(message)
        or "maximum groq request budget" in message.lower()
        or "daily token limit has been reached" in message.lower()
    )


def _is_daily_token_limit_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "tokens per day" in lowered
        or "tpd" in lowered
        or ("type: tokens" in lowered and "rate_limit_exceeded" in lowered)
    )


def _normalize_confidence_label(value: str) -> str:
    allowed = {"official", "reported", "rumor", "unconfirmed"}
    return value if value in allowed else "reported"


def _normalize_social_confidence_label(value: str) -> str:
    allowed = {"official", "reporter_claim", "rumor", "unconfirmed"}
    return value if value in allowed else "reporter_claim"


def _ensure_article_summary_quality(summary: Dict[str, str]) -> None:
    if (
        _contains_disallowed_script(summary["headline_ko"])
        or _contains_disallowed_script(summary["body_ko"])
        or _is_mostly_untranslated_english(summary["headline_ko"])
        or _is_mostly_untranslated_english(summary["body_ko"])
        or _has_generic_article_headline(summary["headline_ko"])
        or _has_generic_article_body(summary["body_ko"])
    ):
        raise GroqAPIError("Groq article summary failed quality checks.")


def _ensure_social_post_summary_quality(summary: Dict[str, str]) -> None:
    if _contains_disallowed_script(summary["headline_ko"]) or _contains_disallowed_script(summary["body_ko"]):
        raise GroqAPIError("Groq social post summary failed quality checks.")
    if _has_generic_social_headline(summary["headline_ko"]) or _has_generic_social_body(summary["body_ko"]):
        raise GroqAPIError("Groq social post summary failed quality checks.")


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
        "데이비드 오른스타인": "David Ornstein",
        "데이비드 오르니스타인": "David Ornstein",
        "리오 응구모하": "Rio Ngumoha",
        "커티스 존스": "Curtis Jones",
        "페데리코 키에사": "Federico Chiesa",
        "피에데리코 키에사": "Federico Chiesa",
        "파브리치오 로마노": "Fabrizio Romano",
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


def _has_generic_article_headline(value: str) -> bool:
    generic_patterns = (
        "관련 소식",
        "관련 팀 소식",
        "관련 이적 소식",
        "관련 루머 소식",
        "관련 오피셜 소식",
        "관련 부상 소식",
        "리버풀 관련",
        "원문 확인",
    )
    lowered = value.lower()
    return any(pattern in lowered for pattern in generic_patterns)


def _has_generic_article_body(value: str) -> bool:
    generic_patterns = (
        "관련 리버풀 소식을 전했습니다",
        "내용을 전했습니다",
        "원문 확인이 필요",
    )
    lowered = value.lower()
    return any(pattern in lowered for pattern in generic_patterns)


def _has_generic_social_headline(value: str) -> bool:
    generic_patterns = (
        "기자 신호",
        "관련 x 소식",
        "관련 x 업데이트",
        "리버풀 관련 소식",
        "새 소식 없음",
        "원문 확인",
        "x에서 리버풀",
    )
    lowered = value.lower()
    return any(pattern in lowered for pattern in generic_patterns)


def _has_generic_social_body(value: str) -> bool:
    generic_patterns = (
        "원문 확인이 필요",
        "새 소식을 공유하지 않",
        "리버풀 관련 소식을 공유했습니다",
        "관련 리버풀 소식을 전했습니다",
    )
    lowered = value.lower()
    return any(pattern in lowered for pattern in generic_patterns)


def _clean_social_text(value: str) -> str:
    text = value.replace("\n", " ")
    text = " ".join(part for part in text.split() if not part.startswith("http"))
    return " ".join(text.split()).strip()
