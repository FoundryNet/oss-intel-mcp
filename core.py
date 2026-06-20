"""Shared logic behind the MCP tools + REST routes: 6 operations + x402 gating.
license_check and mint_info are free; the paid tools run payment_gate.precheck
(per-tool price from config.TOOL_PRICES) first. project_health / dependency_risk /
trending_repos / compare_packages do live GitHub/PyPI/npm/libraries.io lookups (with
a daily-aggregated cache fallback for trending). Paid results carry a MINT
provenance attestation.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import config
import daily_curator
import mint_integration
import oss_sources as src
import payment_gate
import supa

logger = logging.getLogger("oss.core")


def _billing(d):
    g = d.get("gate")
    if g == "free":
        cap, cnt = d.get("cap"), d.get("count")
        return {"tier": "free", "used_today": cnt, "daily_free": cap,
                "remaining_today": (cap - cnt) if (cap is not None and cnt is not None) else None}
    if g == "paid":
        return {"tier": "paid", "charged_usdc": d.get("amount_usdc")}
    if g == "api_key":
        return {"tier": "api_key", "note": "billed to your Forge account"}
    return {"tier": "free", "note": "gating inert"}


async def _attest(result: dict, summary: str) -> dict:
    """Additive MINT provenance, off the event loop, fail-open."""
    return await asyncio.to_thread(mint_integration.attest_data, result, "analysis", summary)


# ── project_health (PAID $0.01) ──────────────────────────────────────────────
async def do_project_health(repo, *, agent_key, payment_tx=None, api_key=None):
    if not repo:
        return {"error": "bad_request", "detail": "repo is required (owner/name)"}
    dec = await payment_gate.precheck("project_health", {"repo": repo},
                                      config.PRICE_PROJECT_HEALTH, agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    data = await src.github_repo(repo)
    if isinstance(data, dict) and data.get("error"):
        return {**data, "billing": _billing(dec)}
    result = {**data, "billing": _billing(dec)}
    result["provenance"] = await _attest(data, f"project_health {repo}")
    return result


# ── dependency_risk (PAID $0.02) ─────────────────────────────────────────────
async def do_dependency_risk(package_name, ecosystem, *, agent_key, payment_tx=None, api_key=None):
    if not package_name or not ecosystem:
        return {"error": "bad_request", "detail": "package_name and ecosystem are required"}
    dec = await payment_gate.precheck("dependency_risk",
                                      {"package_name": package_name, "ecosystem": ecosystem},
                                      config.PRICE_DEPENDENCY_RISK, agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    data = await src.dependency_risk(package_name, ecosystem)
    if isinstance(data, dict) and data.get("error"):
        return {**data, "billing": _billing(dec)}
    note = None if config.LIBRARIESIO_API_KEY else "Set LIBRARIESIO_API_KEY for dependents/SourceRank/deprecation."
    result = {**data, "note": note, "billing": _billing(dec)}
    result["provenance"] = await _attest(data, f"dependency_risk {package_name}/{ecosystem}")
    return result


# ── trending_repos (PAID $0.01) ──────────────────────────────────────────────
async def do_trending_repos(language, topic, period, *, agent_key, payment_tx=None, api_key=None):
    period = (period or "weekly").lower()
    params = {k: v for k, v in {"language": language, "topic": topic, "period": period}.items()
              if v not in (None, "")}
    dec = await payment_gate.precheck("trending_repos", params, config.PRICE_TRENDING_REPOS,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    # Prefer the daily-aggregated cache when there are no language/topic filters.
    rows, source = [], "live"
    if not language and not topic:
        cached = await supa.trending(period=period, limit=25)
        if cached:
            rows, source = cached, "daily_aggregate"
    if not rows:
        rows = await src.github_trending(language=language, topic=topic, period=period, limit=25)
    result = {"period": period, "language": language, "topic": topic,
              "count": len(rows), "source": source, "results": rows,
              "billing": _billing(dec)}
    result["provenance"] = await _attest({"params": params, "count": len(rows)},
                                         f"trending_repos {period}")
    return result


# ── license_check (FREE) ─────────────────────────────────────────────────────
async def do_license_check(repo, *, agent_key, payment_tx=None, api_key=None):
    if not repo:
        return {"error": "bad_request", "detail": "repo is required (owner/name)"}
    # Price 0 → gate stays open, but route it through precheck for consistency.
    dec = await payment_gate.precheck("license_check", {"repo": repo},
                                      config.PRICE_LICENSE_CHECK, agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    data = await src.github_license(repo)
    return {**data, "billing": _billing(dec)}


# ── compare_packages (PAID $0.01) ────────────────────────────────────────────
async def do_compare_packages(packages, ecosystem, *, agent_key, payment_tx=None, api_key=None):
    pkgs = [p for p in (packages or []) if p and str(p).strip()]
    if not pkgs or not ecosystem:
        return {"error": "bad_request", "detail": "packages (non-empty list) and ecosystem are required"}
    dec = await payment_gate.precheck("compare_packages",
                                      {"packages": pkgs, "ecosystem": ecosystem},
                                      config.PRICE_COMPARE_PACKAGES, agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    rows = await src.compare_packages(pkgs, ecosystem)
    result = {"ecosystem": ecosystem, "count": len(rows), "comparison": rows,
              "note": "lower risk_score is safer; downloads = npm last-month where available",
              "billing": _billing(dec)}
    result["provenance"] = await _attest({"packages": pkgs, "ecosystem": ecosystem},
                                         f"compare_packages {ecosystem}")
    return result


# ── daily_brief (premium, curated) ───────────────────────────────────────────
async def do_daily_brief(date, *, agent_key, payment_tx=None, api_key=None):
    day = (date or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
    dec = await payment_gate.precheck("daily_brief", {"date": day}, config.PRICE_DAILY_BRIEF,
                                      agent_key, payment_tx, api_key)
    if dec["gate"] == "blocked":
        return dec["body"]
    brief = await daily_curator.get_brief(day)
    if not brief:
        return {"error": "not_available",
                "detail": f"No brief for {day} (not yet generated, or expired at midnight UTC). "
                          f"Briefs are curated daily at {config.BRIEF_HOUR_UTC:02d}:00 UTC.",
                "billing": _billing(dec)}
    await daily_curator.bump_purchase(day)
    return {**brief, "billing": _billing(dec)}


def mint_info():
    return {
        "network": "FoundryNet Data Network", **mint_integration.network_feed_block(),
        "message": "Attest your agent's open-source analysis with MINT Protocol for verifiable proof.",
        "mint_protocol": {"mcp_endpoint": config.MINT_MCP_URL, "info_url": config.MINT_INFO_URL,
                          "tools": ["mint_register", "mint_attest", "mint_verify",
                                    "mint_rate", "mint_recommend", "mint_discover"]},
        "see_also": config.SISTER_SERVERS,
    }


# ── Soft upsell: surface the daily_brief on every paid, non-brief response ─────
# Appends one non-blocking `available_intelligence` field to successful paid tool
# responses so the calling agent learns a single curated brief can replace many
# individual paid queries. Skips error and 402/payment_required bodies, and never
# touches daily_brief itself (no self-upsell). Brief status is cached 5 min, so
# this adds no per-call DB latency. Added 2026-06-20 (seller_agent v2 upsell hook).
import time as _upsell_time

_brief_upsell_cache = {"day": None, "ts": 0.0, "available": False, "count": 0}


async def _brief_status_cached() -> tuple[bool, int]:
    day = _upsell_time.strftime("%Y-%m-%d", _upsell_time.gmtime())
    now = _upsell_time.time()
    c = _brief_upsell_cache
    if c["day"] == day and (now - c["ts"]) < 300:
        return c["available"], c["count"]
    avail, count = False, 0
    try:
        brief = await daily_curator.get_brief(day)
        if brief:
            avail, count = True, int(brief.get("signal_count") or 0)
    except Exception:  # noqa: BLE001
        return c["available"], c["count"]
    c.update(day=day, ts=now, available=avail, count=count)
    return avail, count


async def _available_intelligence() -> dict:
    avail, count = await _brief_status_cached()
    return {"daily_brief": {
        "available": avail,
        "signal_count": count,
        "price_usd": config.PRICE_DAILY_BRIEF,
        "tool": "daily_brief",
        "note": "Curated daily intelligence — more efficient than individual queries",
    }}


def _make_upsell(_fn):
    import functools

    @functools.wraps(_fn)
    async def _wrapped(*a, **k):
        result = await _fn(*a, **k)
        if isinstance(result, dict) and "error" not in result and "payment_required" not in result:
            try:
                result["available_intelligence"] = await _available_intelligence()
            except Exception:  # noqa: BLE001
                pass
            try:
                import asyncio as _aio, mint_integration as _mint
                result["foundrynet_network"] = await _aio.to_thread(_mint.network_heartbeat)
            except Exception:  # noqa: BLE001
                pass
        return result

    return _wrapped


for _upsell_fn in ("do_project_health", "do_dependency_risk", "do_trending_repos", "do_license_check", "do_compare_packages",):
    if _upsell_fn in globals():
        globals()[_upsell_fn] = _make_upsell(globals()[_upsell_fn])
