-- Open Source Intelligence — schema for oss_aggregator + oss-intel-mcp.
-- Standalone Supabase project (oss-intel). Idempotent.

create extension if not exists pg_trgm;

-- ── project_health (GitHub repo health cache) ────────────────────────────────
create table if not exists project_health (
  repo              text primary key,        -- owner/name
  stars             integer,
  forks             integer,
  open_issues       integer,
  watchers          integer,
  commit_frequency  numeric,                 -- recent avg commits/week
  last_commit_date  timestamptz,
  contributor_count integer,
  license           text,
  language          text,
  archived          boolean default false,
  description       text,
  health_score      integer,                 -- 0-100 composite
  created_at_repo   timestamptz,
  fetched_at        timestamptz,
  updated_at        timestamptz not null default now()
);
create index if not exists idx_ph_stars on project_health (stars desc nulls last);
create index if not exists idx_ph_score on project_health (health_score desc nulls last);
create index if not exists idx_ph_language on project_health (language);

-- ── dependency_risk (package risk cache) ─────────────────────────────────────
create table if not exists dependency_risk (
  package_name       text not null,
  ecosystem          text not null,          -- npm | pypi | cargo
  version            text,
  license            text,
  maintenance_status text,                   -- active | slow | stale | abandoned | deprecated | unknown
  last_update        timestamptz,
  deprecated_status  boolean default false,
  dependents_count   integer,
  risk_score         integer,                -- 0-100 (higher = riskier)
  data               jsonb,                  -- full computed risk payload
  fetched_at         timestamptz,
  updated_at         timestamptz not null default now(),
  primary key (package_name, ecosystem)
);
create index if not exists idx_dr_risk on dependency_risk (risk_score desc nulls last);
create index if not exists idx_dr_deprecated on dependency_risk (deprecated_status);
create index if not exists idx_dr_ecosystem on dependency_risk (ecosystem);

-- ── trending_repos (daily-aggregated GitHub search) ──────────────────────────
create table if not exists trending_repos (
  repo         text not null,
  period       text not null,                -- daily | weekly
  stars        integer,
  forks        integer,
  open_issues  integer,
  language     text,
  license      text,
  description  text,
  url          text,
  topic        text,
  captured_at  timestamptz,
  updated_at   timestamptz not null default now(),
  primary key (repo, period)
);
create index if not exists idx_tr_period_stars on trending_repos (period, stars desc nulls last);
create index if not exists idx_tr_language on trending_repos (language);

-- ── free-tier counter + payments ─────────────────────────────────────────────
create table if not exists oss_query_usage (
  agent_key text not null, day date not null,
  count integer not null default 0, updated_at timestamptz not null default now(),
  primary key (agent_key, day)
);
create or replace function oss_claim_free_query(p_agent_key text, p_day date, p_cap integer)
returns jsonb language plpgsql as $$
declare cur integer; ok boolean;
begin
  insert into oss_query_usage (agent_key, day, count, updated_at)
  values (p_agent_key, p_day, 0, now())
  on conflict (agent_key, day) do nothing;
  select count into cur from oss_query_usage
    where agent_key = p_agent_key and day = p_day for update;
  if cur < p_cap then
    update oss_query_usage set count = count + 1, updated_at = now()
      where agent_key = p_agent_key and day = p_day;
    ok := true; cur := cur + 1;
  else ok := false; end if;
  return jsonb_build_object('allowed', ok, 'count', cur, 'cap', p_cap);
end; $$;

create table if not exists oss_payments (
  tx_signature text primary key, intent text, agent_key text, tool text,
  amount_usdc numeric, payer_wallet text, recipient text, status text,
  block_time bigint, created_at timestamptz not null default now()
);
