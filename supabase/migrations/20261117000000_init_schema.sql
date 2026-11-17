-- BRIEF-34: 초기 스키마 (briefings / issues / system_logs) 및 멱등 UPSERT
-- BRIEF-19: issues.watch_point 포함
-- 기준 문서: docs/prd.md (US-1~3, US-5, US-8, 비기능 요구사항). proposal.md는 참고용.

create extension if not exists pgcrypto;

-- 1. briefings: 일자당 1건 (재실행 시 UPSERT, PRD US-5·US-8)
-- briefing_date는 KST 기준 일자로 저장 (PRD 비기능: 시간대)
-- market_indicators: 5개 지표(원/달러, 코스피, 나스닥, 미 국채 10년물, WTI)의
--   값·전일 대비 등락률·기준 시각 스냅샷 (US-2). 수집 실패 지표는 value=null.
create table if not exists public.briefings (
  id                uuid primary key default gen_random_uuid(),
  briefing_date     date not null unique,
  published_at      timestamptz not null default now(),
  domestic_top3     jsonb not null default '[]'::jsonb,
  global_top3       jsonb not null default '[]'::jsonb,
  market_indicators jsonb not null default '[]'::jsonb
);

-- 2. issues: 권역·순위 기준 유니크
create table if not exists public.issues (
  id             uuid primary key default gen_random_uuid(),
  briefing_id    uuid not null references public.briefings (id) on delete cascade,
  region_code    varchar(2) not null
                 check (region_code in ('KR', 'US', 'CN', 'JP', 'EU', 'ME')),
  rank           int not null check (rank between 1 and 3),
  keyword        varchar(100) not null,
  fact_one_line  text not null,
  market_impact  text not null,
  -- 비어 있어도 허용 (US-3 인수조건 5), 최대 3줄
  context_3lines jsonb not null default '[]'::jsonb
                 check (jsonb_typeof(context_3lines) = 'array'
                        and jsonb_array_length(context_3lines) <= 3),
  -- 향후 관전 포인트 1줄 (US-3, BRIEF-19)
  watch_point    text,
  source_name    varchar(100) not null,
  source_url     text not null,
  created_at     timestamptz not null default now(),
  constraint issues_briefing_region_rank_key unique (briefing_id, region_code, rank)
);

create index if not exists issues_keyword_idx on public.issues (keyword);
create index if not exists issues_region_created_idx on public.issues (region_code, created_at desc);

-- 3. system_logs: 배치 결과·실패 소스 기록 및 Supabase 7일 일시정지 방지 (US-8)
-- partial = 일부 RSS 소스 실패 (인수조건 3)
create table if not exists public.system_logs (
  id          serial primary key,
  executed_at timestamptz not null default now(),
  status      varchar(20) not null check (status in ('success', 'partial', 'failure')),
  summary     text
);

create index if not exists system_logs_executed_idx on public.system_logs (executed_at desc);

-- RLS: 공개 조회만 허용, 쓰기는 service_role(배치)만 가능
alter table public.briefings   enable row level security;
alter table public.issues      enable row level security;
alter table public.system_logs enable row level security;

drop policy if exists briefings_public_read on public.briefings;
create policy briefings_public_read on public.briefings for select using (true);

drop policy if exists issues_public_read on public.issues;
create policy issues_public_read on public.issues for select using (true);

-- 4. 멱등 UPSERT: 브리핑 + 이슈를 한 트랜잭션으로 갱신
-- p_issues 예: [{"region_code":"US","rank":1,"keyword":"...","fact_one_line":"...",
--   "market_impact":"...","context_3lines":["","",""],"watch_point":"...",
--   "source_name":"...","source_url":"..."}]
create or replace function public.upsert_briefing(
  p_briefing_date     date,
  p_domestic_top3     jsonb,
  p_global_top3       jsonb,
  p_market_indicators jsonb,
  p_issues            jsonb
) returns uuid
language plpgsql
security invoker
as $$
declare
  v_briefing_id uuid;
begin
  insert into public.briefings as b
    (briefing_date, published_at, domestic_top3, global_top3, market_indicators)
  values
    (p_briefing_date, now(), p_domestic_top3, p_global_top3, p_market_indicators)
  on conflict (briefing_date) do update set
    published_at      = now(),
    domestic_top3     = excluded.domestic_top3,
    global_top3       = excluded.global_top3,
    market_indicators = excluded.market_indicators
  returning b.id into v_briefing_id;

  insert into public.issues
    (briefing_id, region_code, rank, keyword, fact_one_line, market_impact,
     context_3lines, watch_point, source_name, source_url)
  select
    v_briefing_id, i.region_code, i.rank, i.keyword, i.fact_one_line, i.market_impact,
    coalesce(i.context_3lines, '[]'::jsonb), i.watch_point, i.source_name, i.source_url
  from jsonb_to_recordset(coalesce(p_issues, '[]'::jsonb)) as i(
    region_code text, rank int, keyword text, fact_one_line text, market_impact text,
    context_3lines jsonb, watch_point text, source_name text, source_url text
  )
  on conflict (briefing_id, region_code, rank) do update set
    keyword        = excluded.keyword,
    fact_one_line  = excluded.fact_one_line,
    market_impact  = excluded.market_impact,
    context_3lines = excluded.context_3lines,
    watch_point    = excluded.watch_point,
    source_name    = excluded.source_name,
    source_url     = excluded.source_url;

  return v_briefing_id;
end;
$$;

revoke all on function public.upsert_briefing(date, jsonb, jsonb, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.upsert_briefing(date, jsonb, jsonb, jsonb, jsonb) to service_role;
