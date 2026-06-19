-- Cybersecurity Threat Intelligence — schema for threat_aggregator + cyber-intel-mcp.
-- Standalone Supabase project. Idempotent.

create extension if not exists pg_trgm;

-- ── vulnerabilities (CVEs enriched w/ EPSS + KEV) ────────────────────────────
create table if not exists vulnerabilities (
  cve_id            text primary key,
  description       text,
  published_date    timestamptz,
  modified_date     timestamptz,
  cvss_v3_score     numeric,
  cvss_v3_severity  text,            -- critical | high | medium | low
  cvss_v3_vector    text,
  attack_vector     text,            -- network | adjacent | local | physical
  attack_complexity text,            -- low | high
  cwe_id            text,
  cwe_name          text,
  affected_products jsonb,           -- CPE matches
  epss_score        numeric,         -- 0-1 probability of exploitation
  epss_percentile   numeric,
  is_kev            boolean default false,
  kev_due_date      date,
  reference_urls    jsonb,           -- array of URLs (named to avoid the SQL reserved word)
  patch_available   boolean,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index if not exists idx_vuln_published on vulnerabilities (published_date desc nulls last);
create index if not exists idx_vuln_severity on vulnerabilities (cvss_v3_severity);
create index if not exists idx_vuln_cvss on vulnerabilities (cvss_v3_score desc nulls last);
create index if not exists idx_vuln_epss on vulnerabilities (epss_score desc nulls last);
create index if not exists idx_vuln_kev on vulnerabilities (is_kev);
create index if not exists idx_vuln_vector on vulnerabilities (attack_vector);
create index if not exists idx_vuln_desc_trgm on vulnerabilities using gin (description gin_trgm_ops);
create index if not exists idx_vuln_products on vulnerabilities using gin (affected_products);

-- ── threat_indicators (IPs/domains/hashes/urls) ──────────────────────────────
create table if not exists threat_indicators (
  id              uuid primary key default gen_random_uuid(),
  indicator_type  text,             -- ip | domain | hash | url
  indicator_value text,
  threat_type     text,             -- malware | phishing | botnet | scanner | spam
  confidence      integer,          -- 0-100
  source          text,
  first_seen      timestamptz,
  last_seen       timestamptz,
  report_count    integer,
  tags            jsonb,
  created_at      timestamptz not null default now(),
  unique (indicator_type, indicator_value, source)
);
create index if not exists idx_ti_value on threat_indicators (indicator_value);
create index if not exists idx_ti_type on threat_indicators (indicator_type);
create index if not exists idx_ti_threat on threat_indicators (threat_type);
create index if not exists idx_ti_lastseen on threat_indicators (last_seen desc nulls last);

-- ── free-tier counter + payments ─────────────────────────────────────────────
create table if not exists cyber_query_usage (
  agent_key text not null, day date not null,
  count integer not null default 0, updated_at timestamptz not null default now(),
  primary key (agent_key, day)
);
create or replace function cyber_claim_free_query(p_agent_key text, p_day date, p_cap integer)
returns jsonb language plpgsql as $$
declare cur integer; ok boolean;
begin
  insert into cyber_query_usage (agent_key, day, count, updated_at)
  values (p_agent_key, p_day, 0, now())
  on conflict (agent_key, day) do nothing;
  select count into cur from cyber_query_usage
    where agent_key = p_agent_key and day = p_day for update;
  if cur < p_cap then
    update cyber_query_usage set count = count + 1, updated_at = now()
      where agent_key = p_agent_key and day = p_day;
    ok := true; cur := cur + 1;
  else ok := false; end if;
  return jsonb_build_object('allowed', ok, 'count', cur, 'cap', p_cap);
end; $$;

create table if not exists cyber_payments (
  tx_signature text primary key, intent text, agent_key text, tool text,
  amount_usdc numeric, payer_wallet text, recipient text, status text,
  block_time bigint, created_at timestamptz not null default now()
);
