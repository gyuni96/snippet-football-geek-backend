from datetime import datetime, timezone
import unittest

from app.freshness import filter_fresh_items, parse_iso_datetime
from app.models import RawItem


class FreshnessTest(unittest.TestCase):
    def test_filters_items_newer_than_since_and_within_retention_days(self):
        now = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
        since = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        fresh = _raw_item("fresh", datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc))
        before_since = _raw_item("before-since", datetime(2026, 6, 6, 7, 0, tzinfo=timezone.utc))
        too_old = _raw_item("too-old", datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc))

        filtered = filter_fresh_items(
            [fresh, before_since, too_old],
            since=since,
            retention_days=7,
            now=now,
        )

        self.assertEqual(filtered, [fresh])

    def test_parse_iso_datetime_accepts_z_suffix(self):
        parsed = parse_iso_datetime("2026-06-06T08:00:00Z")

        self.assertEqual(parsed, datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc))

    def test_filters_items_after_until(self):
        now = datetime(2026, 6, 7, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 6, 6, 15, 0, tzinfo=timezone.utc)
        in_range = _raw_item("in-range", datetime(2026, 6, 6, 14, 30, tzinfo=timezone.utc))
        after_until = _raw_item("after-until", datetime(2026, 6, 6, 15, 30, tzinfo=timezone.utc))

        filtered = filter_fresh_items(
            [in_range, after_until],
            since=None,
            retention_days=7,
            now=now,
            until=until,
        )

        self.assertEqual(filtered, [in_range])


def _raw_item(external_id, published_at):
    return RawItem(
        team_slug="liverpool",
        source_type="rss",
        source_name="Test RSS",
        external_id=external_id,
        url=f"https://example.com/{external_id}",
        title="Liverpool update",
        text="Liverpool update text.",
        published_at=published_at,
    )


if __name__ == "__main__":
    unittest.main()
