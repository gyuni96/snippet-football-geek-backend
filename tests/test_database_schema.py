from pathlib import Path
import unittest


class DatabaseSchemaTest(unittest.TestCase):
    def test_schema_defines_briefing_tables_and_frontend_fields(self):
        schema_path = Path("database/schema.sql")

        self.assertTrue(schema_path.exists(), "database/schema.sql should exist")
        content = schema_path.read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.briefings", content)
        self.assertIn("create table if not exists public.briefing_items", content)
        self.assertIn("create table if not exists public.collector_runs", content)
        self.assertIn("briefing_id uuid not null references public.briefings(id)", content)
        self.assertIn("briefing_id uuid references public.briefings(id) on delete set null", content)
        self.assertIn("status text not null", content)
        self.assertIn("set search_path = ''", content)
        self.assertIn("check (status in ('success', 'warning', 'failed'))", content)
        self.assertIn("source_keys text[] not null", content)
        self.assertIn("item_count integer not null", content)
        self.assertIn("item_type text not null", content)
        self.assertIn("'article'", content)
        self.assertIn("'social_post'", content)
        self.assertIn("category text not null", content)
        self.assertIn("published_at timestamptz", content)
        self.assertIn("event_at timestamptz", content)
        self.assertIn("'transfer'", content)
        self.assertIn("'injury'", content)
        self.assertIn("'match_result'", content)
        self.assertIn("'match_schedule'", content)
        self.assertIn("create index if not exists idx_briefing_items_item_type", content)
        self.assertIn("create index if not exists idx_briefing_items_published_at", content)
        self.assertIn("create index if not exists idx_briefing_items_event_at", content)
        self.assertIn("create index if not exists idx_collector_runs_team_created_at", content)
        self.assertIn("create index if not exists idx_collector_runs_briefing_id", content)
        self.assertIn("alter table public.briefings enable row level security", content)
        self.assertIn("alter table public.briefing_items enable row level security", content)
        self.assertIn("alter table public.collector_runs enable row level security", content)
        self.assertIn("create policy briefings_public_select", content)
        self.assertIn("create policy briefing_items_public_select", content)
        self.assertIn("create policy collector_runs_service_role_all", content)
        self.assertIn("create trigger set_briefings_updated_at", content)
        self.assertIn("create or replace view public.latest_team_briefings", content)
        self.assertIn("with (security_invoker = true)", content)
        self.assertIn("distinct on (team_slug)", content)
        self.assertIn("delete from public.briefings", content)


if __name__ == "__main__":
    unittest.main()
