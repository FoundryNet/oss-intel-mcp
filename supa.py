"""Supabase PostgREST client for oss-intel-mcp (standalone project).

Generic select/rpc/upsert helpers + free-tier/payment ledger, plus reads/writes
for the aggregated caches: project_health, dependency_risk, trending_repos.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import config
from http_util import request_json

logger = logging.getLogger("oss.supa")


def configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


def _headers(extra: Optional[dict] = None) -> dict:
    h = {"apikey": config.SUPABASE_SERVICE_KEY,
         "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
         "Content-Type": "application/json", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _url(path: str) -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{path}"


async def select(table: str, params: dict) -> list:
    if not configured():
        return []
    r = await request_json("GET", _url(table), headers=_headers(), params=params,
                           timeout=config.REQUEST_TIMEOUT)
    return r if isinstance(r, list) else []


async def rpc(fn: str, body: dict):
    if not configured():
        return None
    return await request_json("POST", _url(f"rpc/{fn}"), headers=_headers(), body=body,
                              timeout=config.REQUEST_TIMEOUT)


async def upsert(table: str, rows: list, on_conflict: str) -> dict:
    if not configured() or not rows:
        return {"data": []}
    r = await request_json("POST", _url(table),
                           headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                           params={"on_conflict": on_conflict},
                           body=rows, timeout=max(config.REQUEST_TIMEOUT, 60))
    if isinstance(r, dict) and r.get("error"):
        return r
    return {"data": rows}


async def _bulk_upsert(table: str, rows: list, on_conflict: str) -> int:
    if not configured() or not rows:
        return 0
    seen, deduped = set(), []
    keys = on_conflict.split(",")
    for r in rows:
        k = tuple(r.get(c) for c in keys)
        if any(x is None for x in k) or k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    allkeys = set()
    for r in deduped:
        allkeys.update(r.keys())
    deduped = [{k: r.get(k) for k in allkeys} for r in deduped]
    written = 0
    for i in range(0, len(deduped), 500):
        resp = await request_json("POST", _url(table),
                                  headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                                  params={"on_conflict": on_conflict},
                                  body=deduped[i:i + 500], timeout=max(config.REQUEST_TIMEOUT, 60))
        if isinstance(resp, dict) and resp.get("error"):
            logger.warning(f"upsert {table} chunk {i}: {str(resp)[:200]}")
        else:
            written += len(deduped[i:i + 500])
    return written


# ── cache writes (aggregator) ─────────────────────────────────────────────────
async def upsert_health(rows: list) -> int:
    return await _bulk_upsert("project_health", rows, "repo")


async def upsert_risk(rows: list) -> int:
    return await _bulk_upsert("dependency_risk", rows, "package_name,ecosystem")


async def upsert_trending(rows: list) -> int:
    return await _bulk_upsert("trending_repos", rows, "repo,period")


# ── cache reads (tools) ───────────────────────────────────────────────────────
async def health_by_repo(repo: str) -> Optional[dict]:
    rows = await select("project_health", {"select": "*", "repo": f"eq.{repo}", "limit": "1"})
    return rows[0] if rows else None


async def risk_by_package(name: str, ecosystem: str) -> Optional[dict]:
    rows = await select("dependency_risk", {"select": "*", "package_name": f"eq.{name}",
                                            "ecosystem": f"eq.{ecosystem}", "limit": "1"})
    return rows[0] if rows else None


async def trending(*, period: str = "weekly", language: str | None = None,
                   topic: str | None = None, limit: int = 25) -> list:
    p = {"select": "*", "order": "stars.desc.nullslast", "limit": str(min(max(int(limit or 25), 1), 100))}
    if period:
        p["period"] = f"eq.{period}"
    if language:
        p["language"] = f"eq.{language}"
    if topic:
        p["topic"] = f"eq.{topic}"
    return await select("trending_repos", p)


# ── free-tier + payments ──────────────────────────────────────────────────────
async def claim_free_query(agent_key: str, day: str, cap: int) -> Optional[dict]:
    r = await rpc("oss_claim_free_query", {"p_agent_key": agent_key, "p_day": day, "p_cap": cap})
    if isinstance(r, dict) and "allowed" in r:
        return r
    if isinstance(r, list) and r and isinstance(r[0], dict):
        return r[0]
    return None


async def payment_tx_used(tx_signature: str) -> bool:
    rows = await select("oss_payments", {"tx_signature": f"eq.{tx_signature}",
                                         "select": "tx_signature", "limit": "1"})
    return bool(rows)


async def insert_payment(row: dict) -> dict:
    if not configured():
        return {"error": "not_configured"}
    r = await request_json("POST", _url("oss_payments"),
                           headers=_headers({"Prefer": "return=minimal"}),
                           body=row, timeout=config.REQUEST_TIMEOUT)
    if isinstance(r, dict) and r.get("error"):
        return r
    return {"data": [row]}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
