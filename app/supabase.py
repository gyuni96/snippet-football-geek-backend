"""Supabase REST API에 브리핑 payload를 저장합니다."""

import json
from urllib.parse import urlencode
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.models import BriefingPayload


HttpRequest = Callable[[str, str, Dict[str, str], Optional[bytes]], Any]


class SupabaseAPIError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(
        self,
        base_url: str,
        service_role_key: str,
        http_request: Optional[HttpRequest] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.service_role_key = service_role_key
        self.http_request = http_request or _http_request_json

    def post(self, path: str, body: Any) -> Any:
        try:
            return self.http_request(
                f"{self.base_url}/rest/v1/{path.lstrip('/')}",
                "POST",
                self._headers(),
                json.dumps(body, ensure_ascii=False).encode("utf-8"),
            )
        except HTTPError as error:
            raise SupabaseAPIError(_format_http_error(error)) from error

    def get(self, path: str) -> Any:
        try:
            return self.http_request(
                f"{self.base_url}/rest/v1/{path.lstrip('/')}",
                "GET",
                self._headers(),
                None,
            )
        except HTTPError as error:
            raise SupabaseAPIError(_format_http_error(error)) from error

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }


def save_briefing_payload(payload: BriefingPayload, client: SupabaseClient) -> str:
    payload_dict = payload.to_dict()
    briefing_rows = client.post(
        "briefings?select=id",
        {
            "team_slug": payload.team_slug,
            "briefing_type": payload.briefing_type,
            "title": payload.title,
            "summary_ko": payload.summary_ko,
            "published_at": payload.published_at.isoformat(),
            "raw_payload": payload_dict,
        },
    )
    briefing_id = briefing_rows[0]["id"]

    if payload.items:
        client.post(
            "briefing_items",
            [
                _briefing_item_row(briefing_id, index, item.to_dict())
                for index, item in enumerate(payload.items)
            ],
        )

    return str(briefing_id)


def save_collector_run(
    client: SupabaseClient,
    team_slug: str,
    briefing_type: str,
    status: str,
    source_keys: List[str],
    item_count: int,
    article_count: int,
    social_post_count: int,
    briefing_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> str:
    rows = client.post(
        "collector_runs?select=id",
        {
            "team_slug": team_slug,
            "briefing_type": briefing_type,
            "status": status,
            "source_keys": source_keys,
            "item_count": item_count,
            "article_count": article_count,
            "social_post_count": social_post_count,
            "briefing_id": briefing_id,
            "error_message": error_message,
        },
    )
    return str(rows[0]["id"])


def fetch_latest_briefing_published_at(
    client: SupabaseClient,
    team_slug: str,
) -> Optional[str]:
    query = urlencode(
        {
            "select": "published_at",
            "team_slug": f"eq.{team_slug}",
            "order": "published_at.desc",
            "limit": "1",
        }
    )
    rows = client.get(f"briefings?{query}")
    if not rows:
        return None
    return str(rows[0]["published_at"])


def _briefing_item_row(briefing_id: str, sort_order: int, item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "briefing_id": briefing_id,
        "sort_order": sort_order,
        "section": item["section"],
        "headline_ko": item["headline_ko"],
        "body_ko": item["body_ko"],
        "category": item["category"],
        "category_label_ko": item["category_label_ko"],
        "item_type": item["source_type"],
        "confidence_label": item["confidence_label"],
        "source_count": item["source_count"],
        "source_urls": item["source_urls"],
        "source_names": item["source_names"],
    }


def _http_request_json(url: str, method: str, headers: Dict[str, str], body: Optional[bytes]) -> Any:
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        response_body = response.read().decode("utf-8")
    return json.loads(response_body) if response_body else None


def _format_http_error(error: HTTPError) -> str:
    body = error.read().decode("utf-8", errors="replace")
    return f"Supabase API request failed with status {error.code}: {body}"
