"""배치 실행 결과를 외부 알림 채널로 전송합니다.

현재는 Discord webhook을 지원합니다. 수집 파이프라인 본문과 분리해 두면
나중에 Slack, Telegram 같은 알림 채널을 같은 방식으로 추가할 수 있습니다.
"""

import json
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.models import BriefingPayload


HttpRequest = Callable[[str, str, Dict[str, str], Optional[bytes]], Any]


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: str,
        http_request: Optional[HttpRequest] = None,
    ):
        self.webhook_url = webhook_url
        self.http_request = http_request or _http_request

    def send(self, message: Dict[str, Any]) -> None:
        try:
            self.http_request(
                self.webhook_url,
                "POST",
                {
                    "Content-Type": "application/json",
                    "User-Agent": "SnippetFootballGeek/1.0",
                },
                json.dumps(message, ensure_ascii=False).encode("utf-8"),
            )
        except HTTPError as error:
            body = _read_error_body(error)
            suffix = f": {body}" if body else ""
            raise RuntimeError(f"Discord webhook request failed with status {error.code}{suffix}") from error


def build_discord_run_message(
    team_slug: str,
    briefing_type: str,
    status: str,
    source_keys: List[str],
    payload: Optional[BriefingPayload],
    briefing_id: Optional[str],
    error_message: Optional[str] = None,
    github_run_url: Optional[str] = None,
    x_auth_issue_handles: Optional[List[str]] = None,
    groq_issue_messages: Optional[List[str]] = None,
    groq_primary_model: Optional[str] = None,
    groq_current_model: Optional[str] = None,
    groq_fallback_models: Optional[List[str]] = None,
    collection_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    items = payload.items if payload is not None else []
    article_count = sum(1 for item in items if item.source_type == "article")
    social_post_count = sum(1 for item in items if item.source_type == "social_post")
    status_meta = _notification_status_meta(status)
    fields = [
        {"name": "팀", "value": team_slug, "inline": True},
        {"name": "브리핑", "value": briefing_type, "inline": True},
        {
            "name": "항목",
            "value": f"총 {len(items)}개 / 기사 {article_count}개 / X {social_post_count}개",
            "inline": False,
        },
    ]
    if github_run_url:
        fields.append({"name": "GitHub Actions", "value": github_run_url, "inline": False})
    groq_model_field = _build_groq_model_field(
        primary_model=groq_primary_model,
        current_model=groq_current_model,
        fallback_models=groq_fallback_models or [],
    )
    if groq_model_field:
        fields.append({"name": "🤖 Groq 모델", "value": groq_model_field, "inline": False})
    collection_debug_field = _build_collection_debug_field(collection_counts or {})
    if collection_debug_field:
        fields.append({"name": "📊 수집 흐름", "value": collection_debug_field, "inline": False})
    if x_auth_issue_handles:
        handles = ", ".join(f"@{handle}" for handle in x_auth_issue_handles)
        fields.append({"name": "⚠️ X 인증 상태", "value": f"⚠️ 토큰/쿠키 만료 의심: {handles}", "inline": False})
    if groq_issue_messages:
        messages = [_humanize_groq_issue_message(message) for message in dict.fromkeys(groq_issue_messages)]
        fields.append(
            {
                "name": "⚠️ Groq 상태",
                "value": _trim_discord_field("⚠️ " + "\n".join(messages)),
                "inline": False,
            }
        )
    if error_message:
        fields.append({"name": "오류", "value": _trim_discord_field(error_message), "inline": False})

    return {
        "content": status_meta["content"],
        "embeds": [
            {
                "title": status_meta["title"],
                "color": status_meta["color"],
                "fields": fields,
            }
        ],
    }


def _build_groq_model_field(
    primary_model: Optional[str],
    current_model: Optional[str],
    fallback_models: List[str],
) -> Optional[str]:
    if not primary_model and not current_model and not fallback_models:
        return None
    lines = []
    if primary_model:
        lines.append(f"시작: {primary_model}")
    if current_model:
        lines.append(f"현재: {current_model}")
    if fallback_models:
        lines.append(f"fallback: {', '.join(fallback_models)}")
    return _trim_discord_field("\n".join(lines))


def _build_collection_debug_field(collection_counts: Dict[str, int]) -> Optional[str]:
    if not collection_counts:
        return None
    article_candidate_count = collection_counts.get("article_candidate_count", 0)
    social_post_candidate_count = collection_counts.get("social_post_candidate_count", 0)
    article_output_count = collection_counts.get("article_output_count", 0)
    social_post_output_count = collection_counts.get("social_post_output_count", 0)
    article_unused_count = max(article_candidate_count - article_output_count, 0)
    social_post_unused_count = max(social_post_candidate_count - social_post_output_count, 0)
    return _trim_discord_field(
        "\n".join(
            [
                f"원본 {collection_counts.get('raw_item_count', 0)}개 → 최신 {collection_counts.get('fresh_item_count', 0)}개",
                (
                    "관련성 통과: "
                    f"기사 {collection_counts.get('relevant_article_count', 0)}개 / "
                    f"X {collection_counts.get('relevant_social_post_count', 0)}개"
                ),
                f"요약 후보: 기사 {article_candidate_count}개 / X {social_post_candidate_count}개",
                f"저장 대상: 기사 {article_output_count}개 / X {social_post_output_count}개",
                f"제외/미사용: 기사 {article_unused_count}개 / X {social_post_unused_count}개",
            ]
        )
    )


def _humanize_groq_issue_message(message: str) -> str:
    lowered = message.lower()
    if "daily token limit has been reached" in lowered:
        return "Groq 일일 토큰 한도 초과로 남은 요약 요청을 건너뜁니다."
    if "maximum groq request budget" in lowered:
        return "실행 1회 Groq 요청 예산을 사용해 남은 요약 요청을 건너뜁니다."
    return message


def _trim_discord_field(value: str) -> str:
    return value if len(value) <= 1000 else f"{value[:997]}..."


def _notification_status_meta(status: str) -> Dict[str, Any]:
    if status == "warning":
        return {
            "content": "⚠️ 부분 수집 완료",
            "title": "⚠️ Liverpool Briefing 부분 수집",
            "color": 0xF1C40F,
        }
    if status == "failed":
        return {
            "content": "❌ 수집 실패",
            "title": "❌ Liverpool Briefing 수집 실패",
            "color": 0xE74C3C,
        }
    return {
        "content": "✅ 수집 완료",
        "title": "✅ Liverpool Briefing 수집 성공",
        "color": 0x2ECC71,
    }


def _read_error_body(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _http_request(url: str, method: str, headers: Dict[str, str], body: Optional[bytes]) -> None:
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        response.read()
