#!/usr/bin/env python3
"""oss_aggregator — daily. Refreshes trending repositories (GitHub search) plus a
watchlist of popular repos' health and popular packages' dependency-risk into
Supabase (trending_repos, project_health, dependency_risk). The trending_repos
tool is served from this aggregated table; project_health/dependency_risk read
through to the live source but seed/refresh their caches here.

Manual entry point:
  python oss_aggregator.py            # trending + full watchlist refresh
"""
from __future__ import annotations

import asyncio
import logging
import sys

import config
import oss_sources as src
import supa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("oss.agg")


async def run_aggregation(_unused: int | None = None) -> dict:
    # ── trending repos (daily + weekly, no filters) ──────────────────────────
    trending_rows = []
    for period in ("daily", "weekly"):
        rows = await src.github_trending(period=period, limit=25)
        for r in rows:
            trending_rows.append({
                "repo": r.get("repo"), "period": period, "stars": r.get("stars"),
                "forks": r.get("forks"), "open_issues": r.get("open_issues"),
                "language": r.get("language"), "license": r.get("license"),
                "description": r.get("description"), "url": r.get("url"),
                "topic": None, "captured_at": supa.now_iso(),
            })
    written_t = await supa.upsert_trending(trending_rows)
    log.info(f"trending_repos: upserted {written_t}")

    # ── watchlist repo health ────────────────────────────────────────────────
    health_rows = []
    for repo in config.WATCHLIST_REPOS:
        h = await src.github_repo(repo)
        if isinstance(h, dict) and not h.get("error"):
            health_rows.append({**h, "fetched_at": supa.now_iso()})
    written_h = await supa.upsert_health(health_rows)
    log.info(f"project_health: upserted {written_h}")

    # ── watchlist package risk ───────────────────────────────────────────────
    risk_rows = []
    for p in config.WATCHLIST_PACKAGES:
        r = await src.dependency_risk(p["name"], p["ecosystem"])
        if isinstance(r, dict) and not r.get("error"):
            risk_rows.append({
                "package_name": r.get("package_name"), "ecosystem": r.get("ecosystem"),
                "version": r.get("version"), "license": r.get("license"),
                "maintenance_status": r.get("maintenance_status"),
                "last_update": r.get("last_update"),
                "deprecated_status": r.get("deprecated_status"),
                "dependents_count": r.get("dependents_count"),
                "risk_score": r.get("risk_score"),
                "data": r, "fetched_at": supa.now_iso(),
            })
    written_r = await supa.upsert_risk(risk_rows)
    log.info(f"dependency_risk: upserted {written_r}")

    out = {"trending_written": written_t, "health_written": written_h,
           "risk_written": written_r}
    log.info(f"done: {out}")
    return out


async def main() -> None:
    print(await run_aggregation())


if __name__ == "__main__":
    asyncio.run(main())
