-- Snippet Football Geek Supabase schema
-- MVP는 브리핑 단위와 브리핑 항목 단위를 분리해 저장합니다.
-- 프론트엔드는 briefings를 조회한 뒤 briefing_items를 함께 읽어 카드 UI를 구성합니다.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create table if not exists public.briefings (
    id uuid primary key default gen_random_uuid(),
    team_slug text not null,
    briefing_type text not null,
    title text not null,
    summary_ko text not null,
    published_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    constraint briefings_team_slug_check
        check (team_slug <> ''),
    constraint briefings_briefing_type_check
        check (briefing_type in ('morning', 'afternoon', 'evening', 'transfer_extra', 'matchday')),
    constraint briefings_unique_run
        unique (team_slug, briefing_type, published_at)
);

create table if not exists public.briefing_items (
    id uuid primary key default gen_random_uuid(),
    briefing_id uuid not null references public.briefings(id) on delete cascade,
    sort_order integer not null,
    section text not null,
    headline_ko text not null,
    body_ko text not null,
    category text not null,
    category_label_ko text not null,
    item_type text not null,
    confidence_label text not null,
    source_count integer not null default 1,
    source_urls text[] not null default '{}',
    source_names text[] not null default '{}',
    published_at timestamptz,
    event_at timestamptz,
    created_at timestamptz not null default now(),
    constraint briefing_items_sort_order_check
        check (sort_order >= 0),
    constraint briefing_items_source_count_check
        check (source_count >= 1),
    constraint briefing_items_section_check
        check (section in ('top_stories', 'reporter_signals', 'match_schedule')),
    constraint briefing_items_category_check
        check (category in ('transfer', 'injury', 'match_result', 'match_preview', 'team_news', 'official', 'rumor', 'etc')),
    constraint briefing_items_item_type_check
        check (item_type in ('article', 'social_post')),
    constraint briefing_items_confidence_label_check
        check (confidence_label in ('official', 'reported', 'rumor', 'unconfirmed', 'reporter_claim')),
    constraint briefing_items_unique_order
        unique (briefing_id, sort_order)
);

create table if not exists public.collector_runs (
    id uuid primary key default gen_random_uuid(),
    team_slug text not null,
    briefing_type text not null,
    status text not null,
    source_keys text[] not null default '{}',
    item_count integer not null default 0,
    article_count integer not null default 0,
    social_post_count integer not null default 0,
    briefing_id uuid references public.briefings(id) on delete set null,
    error_message text,
    created_at timestamptz not null default now(),
    constraint collector_runs_team_slug_check
        check (team_slug <> ''),
    constraint collector_runs_briefing_type_check
        check (briefing_type in ('morning', 'afternoon', 'evening', 'transfer_extra', 'matchday')),
    constraint collector_runs_status_check
        check (status in ('success', 'warning', 'failed')),
    constraint collector_runs_item_count_check
        check (item_count >= 0),
    constraint collector_runs_article_count_check
        check (article_count >= 0),
    constraint collector_runs_social_post_count_check
        check (social_post_count >= 0)
);

create index if not exists idx_briefings_team_published_at
    on public.briefings (team_slug, published_at desc);

create index if not exists idx_briefings_type_published_at
    on public.briefings (team_slug, briefing_type, published_at desc);

create index if not exists idx_briefing_items_briefing_order
    on public.briefing_items (briefing_id, sort_order);

create index if not exists idx_briefing_items_category
    on public.briefing_items (category);

create index if not exists idx_briefing_items_item_type
    on public.briefing_items (item_type);

create index if not exists idx_briefing_items_published_at
    on public.briefing_items (briefing_id, published_at desc nulls last, sort_order);

create index if not exists idx_briefing_items_event_at
    on public.briefing_items (briefing_id, event_at desc nulls last, published_at desc nulls last, sort_order);

create index if not exists idx_collector_runs_team_created_at
    on public.collector_runs (team_slug, created_at desc);

create index if not exists idx_collector_runs_briefing_id
    on public.collector_runs (briefing_id);

create index if not exists idx_collector_runs_status_created_at
    on public.collector_runs (status, created_at desc);

drop trigger if exists set_briefings_updated_at on public.briefings;
create trigger set_briefings_updated_at
    before update on public.briefings
    for each row
    execute function public.set_updated_at();

alter table public.briefings enable row level security;
alter table public.briefing_items enable row level security;
alter table public.collector_runs enable row level security;

drop policy if exists briefings_public_select on public.briefings;
create policy briefings_public_select
    on public.briefings
    for select
    to anon, authenticated
    using (true);

drop policy if exists briefing_items_public_select on public.briefing_items;
create policy briefing_items_public_select
    on public.briefing_items
    for select
    to anon, authenticated
    using (true);

drop policy if exists collector_runs_service_role_all on public.collector_runs;
create policy collector_runs_service_role_all
    on public.collector_runs
    for all
    to service_role
    using (true)
    with check (true);

create or replace view public.latest_team_briefings
with (security_invoker = true)
as
select distinct on (team_slug)
    id,
    team_slug,
    briefing_type,
    title,
    summary_ko,
    published_at,
    created_at,
    updated_at
from public.briefings
order by team_slug, published_at desc;

-- 최신 소식 서비스 정책: 기본적으로 7일이 지난 브리핑은 삭제합니다.
-- GitHub Actions나 Supabase scheduled job에서 주기적으로 실행하면 됩니다.
delete from public.briefings
where published_at < now() - interval '7 days';
