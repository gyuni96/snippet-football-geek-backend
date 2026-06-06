from pathlib import Path
import unittest


class DatabaseSchemaTest(unittest.TestCase):
    def test_schema_defines_briefing_tables_and_frontend_fields(self):
        schema_path = Path("database/schema.sql")

        self.assertTrue(schema_path.exists(), "database/schema.sql should exist")
        content = schema_path.read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.briefings", content)
        self.assertIn("create table if not exists public.briefing_items", content)
        self.assertIn("briefing_id uuid not null references public.briefings(id)", content)
        self.assertIn("item_type text not null", content)
        self.assertIn("'article'", content)
        self.assertIn("'social_post'", content)
        self.assertIn("category text not null", content)
        self.assertIn("'transfer'", content)
        self.assertIn("'injury'", content)
        self.assertIn("'match_result'", content)
        self.assertIn("create index if not exists idx_briefing_items_item_type", content)
        self.assertIn("alter table public.briefings enable row level security", content)
        self.assertIn("alter table public.briefing_items enable row level security", content)
        self.assertIn("create policy briefings_public_select", content)
        self.assertIn("create policy briefing_items_public_select", content)
        self.assertIn("create trigger set_briefings_updated_at", content)
        self.assertIn("create or replace view public.latest_team_briefings", content)
        self.assertIn("with (security_invoker = true)", content)
        self.assertIn("distinct on (team_slug)", content)
        self.assertIn("delete from public.briefings", content)


if __name__ == "__main__":
    unittest.main()
