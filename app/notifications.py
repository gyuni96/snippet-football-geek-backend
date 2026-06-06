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
    if x_auth_issue_handles:
        handles = ", ".join(f"@{handle}" for handle in x_auth_issue_handles)
        fields.append({"name": "⚠️ X 인증 상태", "value": f"⚠️ 토큰/쿠키 만료 의심: {handles}", "inline": False})
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
