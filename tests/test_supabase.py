from datetime import datetime, timezone
import json
import unittest

from app.models import BriefingItem, BriefingPayload
from app.supabase import (
    SupabaseClient,
    fetch_latest_briefing_published_at,
    save_briefing_payload,
    save_collector_run,
)


class SupabaseClientTest(unittest.TestCase):
    def test_save_briefing_payload_inserts_briefing_and_items(self):
        requests = []

        def fake_http_request(url, method, headers, body):
            requests.append(
                {
                    "url": url,
                    "method": method,
                    "headers": headers,
                    "body": json.loads(body.decode("utf-8")) if body else None,
                }
            )
            if "/briefings" in url:
                return [{"id": "briefing-id-1"}]
            return []

        payload = BriefingPayload(
            team_slug="liverpool",
            briefing_type="morning",
            title="리버풀 아침 브리핑",
            summary_ko="출근길에 확인할 리버풀 핵심 소식 1건입니다.",
            published_at=datetime(2026, 6, 6, 7, 30, tzinfo=timezone.utc),
            items=[
                BriefingItem(
                    section="top_stories",
                    headline_ko="리버풀, 이적 후보 주시",
                    body_ko="리버풀이 이적 후보를 지켜보고 있다는 보도입니다.",
                    category="transfer",
                    category_label_ko="이적",
                    source_count=1,
                    confidence_label="reported",
                    source_urls=["https://example.com/news"],
                    source_names=["Liverpool Echo"],
                    source_type="article",
                    published_at=datetime(2026, 6, 6, 8, 10, tzinfo=timezone.utc),
                    event_at=datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc),
                )
            ],
        )
        client = SupabaseClient(
            base_url="https://example.supabase.co",
            service_role_key="service-key",
            http_request=fake_http_request,
        )

        briefing_id = save_briefing_payload(payload, client)

        self.assertEqual(briefing_id, "briefing-id-1")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["method"], "POST")
        self.assertIn("/rest/v1/briefings?select=id", requests[0]["url"])
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer service-key")
        self.assertEqual(requests[0]["body"]["team_slug"], "liverpool")
        self.assertEqual(requests[0]["body"]["raw_payload"], payload.to_dict())
        self.assertEqual(requests[1]["body"][0]["briefing_id"], "briefing-id-1")
        self.assertEqual(requests[1]["body"][0]["sort_order"], 0)
        self.assertEqual(requests[1]["body"][0]["item_type"], "article")
        self.assertEqual(requests[1]["body"][0]["category"], "transfer")
        self.assertEqual(requests[1]["body"][0]["published_at"], "2026-06-06T08:10:00+00:00")
        self.assertEqual(requests[1]["body"][0]["event_at"], "2026-08-02T20:00:00+00:00")

    def test_fetch_latest_briefing_published_at_reads_most_recent_row(self):
        requests = []

        def fake_http_request(url, method, headers, body):
            requests.append({"url": url, "method": method, "body": body})
            return [{"published_at": "2026-06-06T09:00:00+00:00"}]

        client = SupabaseClient(
            base_url="https://example.supabase.co",
            service_role_key="service-key",
            http_request=fake_http_request,
        )

        published_at = fetch_latest_briefing_published_at(
            client,
            team_slug="liverpool",
        )

        self.assertEqual(published_at, "2026-06-06T09:00:00+00:00")
        self.assertEqual(requests[0]["method"], "GET")
        self.assertIsNone(requests[0]["body"])
        self.assertIn("/rest/v1/briefings?", requests[0]["url"])
        self.assertIn("team_slug=eq.liverpool", requests[0]["url"])
        self.assertNotIn("briefing_type=eq.", requests[0]["url"])
        self.assertIn("order=published_at.desc", requests[0]["url"])

    def test_save_collector_run_inserts_monitoring_row(self):
        requests = []

        def fake_http_request(url, method, headers, body):
            requests.append(
                {
                    "url": url,
                    "method": method,
                    "body": json.loads(body.decode("utf-8")) if body else None,
                }
            )
            return [{"id": "run-id-1"}]

        client = SupabaseClient(
            base_url="https://example.supabase.co",
            service_role_key="service-key",
            http_request=fake_http_request,
        )

        run_id = save_collector_run(
            client,
            team_slug="liverpool",
            briefing_type="morning",
            status="success",
            source_keys=["all"],
            item_count=5,
            article_count=4,
            social_post_count=1,
            briefing_id="briefing-id-1",
            error_message=None,
        )

        self.assertEqual(run_id, "run-id-1")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertIn("/rest/v1/collector_runs?select=id", requests[0]["url"])
        self.assertEqual(requests[0]["body"]["team_slug"], "liverpool")
        self.assertEqual(requests[0]["body"]["status"], "success")
        self.assertEqual(requests[0]["body"]["source_keys"], ["all"])
        self.assertEqual(requests[0]["body"]["item_count"], 5)
        self.assertEqual(requests[0]["body"]["article_count"], 4)
        self.assertEqual(requests[0]["body"]["social_post_count"], 1)
        self.assertEqual(requests[0]["body"]["briefing_id"], "briefing-id-1")


if __name__ == "__main__":
    unittest.main()
