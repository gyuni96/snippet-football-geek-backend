from datetime import datetime, timezone
import unittest

from app.models import BriefingItem, BriefingPayload


class BriefingPayloadTest(unittest.TestCase):
    def test_briefing_payload_to_dict_returns_json_ready_shape(self):
        published_at = datetime(2026, 6, 6, 7, 30, tzinfo=timezone.utc)
        payload = BriefingPayload(
            team_slug="liverpool",
            briefing_type="morning",
            title="리버풀 아침 브리핑",
            summary_ko="출근길에 확인할 리버풀 핵심 소식입니다.",
            published_at=published_at,
            items=[
                BriefingItem(
                    section="top_stories",
                    headline_ko="중원 보강 후보 재점화",
                    body_ko="아직 협상 단계는 아니지만 체크할 만한 흐름입니다.",
                    source_count=2,
                    confidence_label="reported",
                    source_urls=["https://example.com/news"],
                )
            ],
        )

        self.assertEqual(
            payload.to_dict(),
            {
                "team_slug": "liverpool",
                "briefing_type": "morning",
                "title": "리버풀 아침 브리핑",
                "summary_ko": "출근길에 확인할 리버풀 핵심 소식입니다.",
                "published_at": "2026-06-06T07:30:00+00:00",
                "items": [
                    {
                        "section": "top_stories",
                        "headline_ko": "중원 보강 후보 재점화",
                        "body_ko": "아직 협상 단계는 아니지만 체크할 만한 흐름입니다.",
                        "source_count": 2,
                        "confidence_label": "reported",
                        "source_urls": ["https://example.com/news"],
                    }
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
