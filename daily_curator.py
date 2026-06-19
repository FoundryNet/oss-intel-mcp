"""Daily curated brief — oss-intel.

Runs once a day at BRIEF_HOUR_UTC (05:00 UTC) as an in-process background task
(same shape as the aggregation loop). It reads the day's aggregated trending repos
+ refreshed package health/risk, packages the most significant items (top trending,
notable dependency risks, newly deprecated, biggest growth), attests the package
through MINT for verifiable provenance, and upserts it into the `daily_briefs`
table. The paid `daily_brief` tool just reads that row back.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import config
import mint_integration
import supa

logger = logging.getLogger("oss.curator")

SERVER = config.SERVER_SLUG
PRICE = config.PRICE_DAILY_BRIEF


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _expires_at(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")


def related_briefs(exclude: str) -> list:
    return [{"server": s, "price": p, "tool": "daily_brief"}
            for s, p in config.NETWORK_BRIEFS.items() if s != exclude]


async def _curate_signals(since_iso: str) -> tuple[dict, int]:
    """Build the oss-intel brief body from today's aggregated caches.
    Returns (signals, count)."""
    # Top trending repos today (weekly window), most stars first.
    trend = await supa.select("trending_repos", {
        "select": "repo,period,stars,forks,language,license,description,url,captured_at",
        "period": "eq.weekly", "order": "stars.desc.nullslast", "limit": "10"})
    top_trending_repos = [{"repo": r.get("repo"), "stars": r.get("stars"),
                           "forks": r.get("forks"), "language": r.get("language"),
                           "license": r.get("license"), "url": r.get("url"),
                           "description": r.get("description")} for r in trend]

    # Notable dependency risks: refreshed packages with the highest risk_score.
    risky = await supa.select("dependency_risk", {
        "select": "package_name,ecosystem,version,risk_score,maintenance_status,"
                  "deprecated_status,last_update,dependents_count",
        "order": "risk_score.desc.nullslast", "limit": "10"})
    notable_dependency_risks = [{"package_name": r.get("package_name"), "ecosystem": r.get("ecosystem"),
                                 "risk_score": r.get("risk_score"),
                                 "maintenance_status": r.get("maintenance_status"),
                                 "last_update": r.get("last_update"),
                                 "dependents_count": r.get("dependents_count")} for r in risky]

    # Newly deprecated packages.
    dep = await supa.select("dependency_risk", {
        "select": "package_name,ecosystem,version,maintenance_status,deprecated_status,last_update",
        "deprecated_status": "eq.true", "order": "last_update.desc.nullslast", "limit": "10"})
    newly_deprecated = [{"package_name": r.get("package_name"), "ecosystem": r.get("ecosystem"),
                         "version": r.get("version"), "last_update": r.get("last_update")} for r in dep]

    # Biggest growth: healthiest/most-active watchlist repos by health_score.
    growth = await supa.select("project_health", {
        "select": "repo,stars,forks,health_score,commit_frequency,last_commit_date,language",
        "order": "health_score.desc.nullslast", "limit": "10"})
    biggest_growth = [{"repo": r.get("repo"), "stars": r.get("stars"),
                       "health_score": r.get("health_score"),
                       "commit_frequency": r.get("commit_frequency"),
                       "language": r.get("language")} for r in growth]

    signals = {
        "top_trending_repos": top_trending_repos,
        "notable_dependency_risks": notable_dependency_risks,
        "newly_deprecated": newly_deprecated,
        "biggest_growth": biggest_growth,
    }
    count = (len(top_trending_repos) + len(notable_dependency_risks)
             + len(newly_deprecated) + len(biggest_growth))
    return signals, count


async def run_curation(date_str: str | None = None) -> dict:
    """Generate, attest, and store today's brief. Idempotent per date (upsert)."""
    date_str = date_str or _today()
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    signals, count = await _curate_signals(since_iso)

    brief = {
        "brief_date": date_str, "server": SERVER, "signal_count": count,
        "signals": signals, "expires_at": _expires_at(date_str),
        "related_briefs": related_briefs(SERVER),
    }
    # Attest for provenance (sync httpx → run off the event loop; fail-open).
    attestation = await asyncio.to_thread(
        mint_integration.attest_data, brief, "analysis",
        f"Daily {SERVER} brief: {count} signals")
    brief["provenance"] = attestation

    row = {
        "brief_date": date_str, "brief_data": brief, "signal_count": count,
        "attestation_hash": attestation.get("attestation_hash"),
        "expires_at": _expires_at(date_str),
    }
    res = await supa.upsert("daily_briefs", [row], "brief_date")
    if isinstance(res, dict) and res.get("error"):
        logger.warning(f"daily brief upsert failed: {str(res)[:200]}")
    else:
        logger.info(f"daily brief stored: {date_str} ({count} signals, "
                    f"attested={attestation.get('mint_verified')})")
    return brief


async def get_brief(date_str: str | None = None) -> dict | None:
    """Read a stored brief; None if missing or expired."""
    date_str = date_str or _today()
    rows = await supa.select("daily_briefs",
                             {"select": "*", "brief_date": f"eq.{date_str}", "limit": "1"})
    if not rows:
        return None
    row = rows[0]
    exp = row.get("expires_at")
    if exp:
        try:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(exp.replace("Z", "+00:00")):
                return None
        except Exception:  # noqa: BLE001
            pass
    return row.get("brief_data")


async def bump_purchase(date_str: str) -> None:
    """Best-effort purchase counter via RPC (no-op if the function is absent)."""
    try:
        await supa.rpc("increment_brief_purchase", {"p_brief_date": date_str})
    except Exception:  # noqa: BLE001
        pass


async def curator_loop() -> None:
    """Sleep until BRIEF_HOUR_UTC each day, then curate. Cancellable."""
    while True:
        now = datetime.now(timezone.utc)
        secs = now.hour * 3600 + now.minute * 60 + now.second
        wait = (config.BRIEF_HOUR_UTC * 3600 - secs) % 86400 or 86400
        try:
            await asyncio.sleep(wait)
            if supa.configured():
                await run_curation()
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001
            logger.warning(f"curator loop error: {e}")
            await asyncio.sleep(3600)
