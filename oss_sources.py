"""Free open-source-intelligence sources + scoring.

GitHub API (repos, contributors, commits, search — keyless low-rate, optional
GITHUB_TOKEN for higher limits), PyPI + npm registry (package metadata, downloads),
and libraries.io (cross-ecosystem dependency metadata + deprecation, optional
LIBRARIESIO_API_KEY). All async via request_json; defensive — every fetch returns
a dict/list and never raises. Composite health_score / risk_score live here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import config
from http_util import request_json

logger = logging.getLogger("oss.src")

_UA = {"User-Agent": config.SOURCE_USER_AGENT, "Accept": "application/json"}

# Coarse license classification for license_check.
_PERMISSIVE = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "0bsd", "unlicense", "zlib"}
_COPYLEFT   = {"gpl-2.0", "gpl-3.0", "agpl-3.0", "lgpl-2.1", "lgpl-3.0", "mpl-2.0", "epl-2.0"}


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": config.SOURCE_USER_AGENT}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:  # noqa: BLE001
        return None


# ── GitHub: project health ───────────────────────────────────────────────────
async def github_repo(repo: str) -> dict:
    """Fetch a repo and derive a 0-100 composite health_score. `repo` = owner/name."""
    repo = (repo or "").strip().strip("/")
    if "/" not in repo:
        return {"error": "bad_request", "detail": "repo must be 'owner/name'"}
    r = await request_json("GET", f"{config.GITHUB_API}/repos/{repo}", headers=_gh_headers(),
                           timeout=config.REQUEST_TIMEOUT)
    if not isinstance(r, dict) or r.get("error"):
        return r if isinstance(r, dict) else {"error": "non_json_response"}
    if r.get("id") is None:
        return {"error": "not_found", "detail": f"GitHub repo {repo} not found"}

    contributors = await _github_contributor_count(repo)
    commit_freq, last_commit = await _github_commit_activity(repo)

    last_push_days = _days_since(r.get("pushed_at"))
    lic = (r.get("license") or {})
    out = {
        "repo": r.get("full_name") or repo,
        "stars": r.get("stargazers_count"),
        "forks": r.get("forks_count"),
        "open_issues": r.get("open_issues_count"),
        "watchers": r.get("subscribers_count"),
        "commit_frequency": commit_freq,            # commits/week (recent avg)
        "last_commit_date": last_commit or r.get("pushed_at"),
        "contributor_count": contributors,
        "license": lic.get("spdx_id") or lic.get("key"),
        "language": r.get("language"),
        "archived": bool(r.get("archived")),
        "created_at": r.get("created_at"),
        "description": (r.get("description") or "")[:300] or None,
    }
    out["health_score"] = _health_score(out, last_push_days)
    return out


async def _github_contributor_count(repo: str) -> int | None:
    # anon=1 + per_page=1 puts the total in the Link header's last page; fall back to list len.
    r = await request_json("GET", f"{config.GITHUB_API}/repos/{repo}/contributors",
                           headers=_gh_headers(), params={"per_page": "100", "anon": "1"},
                           timeout=config.REQUEST_TIMEOUT)
    if isinstance(r, list):
        return len(r)
    return None


async def _github_commit_activity(repo: str) -> tuple[float | None, str | None]:
    """Recent commits/week (avg over available weeks) + the latest commit date."""
    freq = None
    stats = await request_json("GET", f"{config.GITHUB_API}/repos/{repo}/stats/participation",
                               headers=_gh_headers(), timeout=config.REQUEST_TIMEOUT)
    if isinstance(stats, dict) and isinstance(stats.get("all"), list) and stats["all"]:
        weeks = stats["all"][-12:]  # last ~12 weeks
        if weeks:
            freq = round(sum(weeks) / len(weeks), 2)
    last = None
    commits = await request_json("GET", f"{config.GITHUB_API}/repos/{repo}/commits",
                                 headers=_gh_headers(), params={"per_page": "1"},
                                 timeout=config.REQUEST_TIMEOUT)
    if isinstance(commits, list) and commits:
        last = (((commits[0] or {}).get("commit") or {}).get("committer") or {}).get("date")
    return freq, last


def _health_score(d: dict, last_push_days: int | None) -> int:
    """0-100 composite: popularity + activity + maintenance + governance."""
    score = 0.0
    stars = d.get("stars") or 0
    # Popularity (max 30) — log-ish bands.
    for thr, pts in ((50000, 30), (10000, 26), (1000, 20), (100, 12), (10, 6)):
        if stars >= thr:
            score += pts
            break
    # Recency of activity (max 30).
    if last_push_days is not None:
        if last_push_days <= 30:
            score += 30
        elif last_push_days <= 90:
            score += 22
        elif last_push_days <= 365:
            score += 12
        elif last_push_days <= 730:
            score += 5
    # Commit frequency (max 20).
    freq = d.get("commit_frequency")
    if freq is not None:
        score += min(freq, 20)
    # Contributors / bus-factor (max 15).
    contrib = d.get("contributor_count") or 0
    for thr, pts in ((100, 15), (25, 11), (10, 7), (3, 4), (1, 2)):
        if contrib >= thr:
            score += pts
            break
    # Governance: has a license (5).
    if d.get("license") and d.get("license") not in ("NOASSERTION", "noassertion"):
        score += 5
    # Penalties.
    if d.get("archived"):
        score *= 0.4
    return int(max(0, min(100, round(score))))


# ── GitHub: trending repos (search) ──────────────────────────────────────────
async def github_trending(language: str | None = None, topic: str | None = None,
                          period: str = "weekly", limit: int = 25) -> list:
    days = 1 if (period or "weekly").lower() == "daily" else 7
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    q = [f"created:>={since}"]
    if language:
        q.append(f"language:{language}")
    if topic:
        q.append(f"topic:{topic}")
    r = await request_json("GET", f"{config.GITHUB_API}/search/repositories", headers=_gh_headers(),
                           params={"q": " ".join(q), "sort": "stars", "order": "desc",
                                   "per_page": str(min(max(int(limit or 25), 1), 100))},
                           timeout=config.REQUEST_TIMEOUT)
    items = r.get("items") if isinstance(r, dict) else None
    rows = []
    for it in (items or []):
        lic = (it.get("license") or {})
        rows.append({
            "repo": it.get("full_name"),
            "stars": it.get("stargazers_count"),
            "forks": it.get("forks_count"),
            "open_issues": it.get("open_issues_count"),
            "language": it.get("language"),
            "license": lic.get("spdx_id") or lic.get("key"),
            "description": (it.get("description") or "")[:240] or None,
            "created_at": it.get("created_at"),
            "url": it.get("html_url"),
            "period": (period or "weekly").lower(),
            "topic": topic,
        })
    logger.info(f"GitHub trending: {len(rows)} repos (lang={language} topic={topic} period={period})")
    return rows


# ── License check ─────────────────────────────────────────────────────────────
async def github_license(repo: str) -> dict:
    repo = (repo or "").strip().strip("/")
    if "/" not in repo:
        return {"error": "bad_request", "detail": "repo must be 'owner/name'"}
    r = await request_json("GET", f"{config.GITHUB_API}/repos/{repo}/license", headers=_gh_headers(),
                           timeout=config.REQUEST_TIMEOUT)
    lic = (r.get("license") if isinstance(r, dict) else None) or {}
    if not lic:
        return {"repo": repo, "license": None,
                "note": "No detectable LICENSE file (treat as all-rights-reserved)."}
    spdx = (lic.get("spdx_id") or lic.get("key") or "").lower()
    cls = "permissive" if spdx in _PERMISSIVE else "copyleft" if spdx in _COPYLEFT else "other"
    perms, restr = _license_terms(cls)
    return {
        "repo": repo,
        "license": lic.get("spdx_id") or lic.get("key"),
        "license_name": lic.get("name"),
        "classification": cls,
        "permissions": perms,
        "restrictions": restr,
        "commercial_use": cls in ("permissive", "copyleft"),
        "compatibility": _license_compat(cls),
    }


def _license_terms(cls: str) -> tuple[list, list]:
    if cls == "permissive":
        return (["commercial-use", "modification", "distribution", "private-use", "sublicense"],
                ["liability", "warranty"])
    if cls == "copyleft":
        return (["commercial-use", "modification", "distribution", "private-use"],
                ["disclose-source", "same-license", "state-changes", "liability", "warranty"])
    return (["see license text"], ["see license text"])


def _license_compat(cls: str) -> str:
    return {
        "permissive": "Broadly compatible; safe to combine with most licenses including proprietary.",
        "copyleft": "Derivative works must usually be released under the same/compatible copyleft license.",
    }.get(cls, "Unknown — review the license text before combining.")


# ── PyPI / npm: package metadata ──────────────────────────────────────────────
async def pypi_package(name: str) -> dict:
    r = await request_json("GET", f"{config.PYPI_API}/{name}/json", headers=_UA,
                           timeout=config.REQUEST_TIMEOUT)
    if not isinstance(r, dict) or r.get("error"):
        return {"error": "not_found", "detail": f"PyPI package {name} not found"}
    info = r.get("info") or {}
    releases = r.get("releases") or {}
    last_upload = None
    files = r.get("urls") or []
    if files:
        last_upload = files[0].get("upload_time_iso_8601") or files[0].get("upload_time")
    classifiers = info.get("classifiers") or []
    deprecated = any("Inactive" in c or "Development Status :: 7" in c for c in classifiers)
    return {
        "name": info.get("name") or name, "ecosystem": "pypi",
        "version": info.get("version"),
        "summary": (info.get("summary") or "")[:200] or None,
        "license": info.get("license") or _classifier_license(classifiers),
        "home_page": info.get("home_page") or info.get("project_url"),
        "release_count": len(releases),
        "last_update": last_upload,
        "requires": info.get("requires_dist") or [],
        "yanked": bool(files and files[0].get("yanked")),
        "deprecated": deprecated,
    }


def _classifier_license(classifiers: list) -> str | None:
    for c in classifiers:
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return None


async def npm_package(name: str) -> dict:
    r = await request_json("GET", f"{config.NPM_API}/{name}", headers=_UA,
                           timeout=config.REQUEST_TIMEOUT)
    if not isinstance(r, dict) or r.get("error"):
        return {"error": "not_found", "detail": f"npm package {name} not found"}
    dist_tags = r.get("dist-tags") or {}
    latest = dist_tags.get("latest")
    versions = r.get("versions") or {}
    times = r.get("time") or {}
    latest_meta = versions.get(latest) or {}
    deprecated = bool(latest_meta.get("deprecated"))
    return {
        "name": r.get("name") or name, "ecosystem": "npm",
        "version": latest,
        "summary": (r.get("description") or "")[:200] or None,
        "license": _npm_license(r, latest_meta),
        "home_page": r.get("homepage"),
        "release_count": len(versions),
        "last_update": times.get("modified") or (times.get(latest) if latest else None),
        "requires": list((latest_meta.get("dependencies") or {}).keys()),
        "deprecated": deprecated,
        "deprecation_message": latest_meta.get("deprecated") if deprecated else None,
    }


def _npm_license(r: dict, latest_meta: dict) -> str | None:
    lic = latest_meta.get("license") or r.get("license")
    if isinstance(lic, dict):
        return lic.get("type")
    if isinstance(lic, list) and lic:
        first = lic[0]
        return first.get("type") if isinstance(first, dict) else str(first)
    return lic


async def npm_downloads(name: str, period: str = "last-month") -> int | None:
    r = await request_json("GET", f"{config.NPM_DOWNLOADS_API}/point/{period}/{name}", headers=_UA,
                           timeout=config.REQUEST_TIMEOUT)
    if isinstance(r, dict) and isinstance(r.get("downloads"), int):
        return r["downloads"]
    return None


# ── libraries.io (cross-ecosystem; optional key) ─────────────────────────────
_LIO_PLATFORM = {"npm": "NPM", "pypi": "PyPI", "cargo": "Cargo"}


async def librariesio_project(name: str, ecosystem: str) -> dict:
    """Dependents, SourceRank, deprecation, latest release — needs LIBRARIESIO_API_KEY."""
    if not config.LIBRARIESIO_API_KEY:
        return {"available": False, "note": "Set LIBRARIESIO_API_KEY for richer dependency metadata."}
    platform = _LIO_PLATFORM.get((ecosystem or "").lower())
    if not platform:
        return {"available": False, "note": f"Unsupported ecosystem '{ecosystem}' for libraries.io."}
    r = await request_json("GET", f"{config.LIBRARIESIO_API}/{platform}/{name}", headers=_UA,
                           params={"api_key": config.LIBRARIESIO_API_KEY},
                           timeout=config.REQUEST_TIMEOUT)
    if not isinstance(r, dict) or r.get("error"):
        return {"available": False, "note": "libraries.io lookup failed or package not found."}
    return {
        "available": True,
        "rank": r.get("rank"),  # SourceRank 0-30ish
        "dependents_count": r.get("dependents_count"),
        "dependent_repos_count": r.get("dependent_repos_count"),
        "stars": r.get("stars"),
        "status": r.get("status"),  # e.g. "Deprecated", "Removed", null
        "latest_release_number": r.get("latest_release_number"),
        "latest_release_published_at": r.get("latest_release_published_at"),
        "deprecation_reason": r.get("deprecation_reason"),
    }


# ── Dependency risk (composite) ───────────────────────────────────────────────
async def dependency_risk(name: str, ecosystem: str) -> dict:
    eco = (ecosystem or "").lower()
    if eco == "npm":
        pkg = await npm_package(name)
    elif eco == "pypi":
        pkg = await pypi_package(name)
    elif eco == "cargo":
        pkg = {"name": name, "ecosystem": "cargo",
               "note": "Cargo metadata served via libraries.io only.", "deprecated": False}
    else:
        return {"error": "bad_request", "detail": "ecosystem must be npm | pypi | cargo"}
    if isinstance(pkg, dict) and pkg.get("error"):
        return pkg

    lio = await librariesio_project(name, eco)
    downloads = await npm_downloads(name) if eco == "npm" else None

    last_update = pkg.get("last_update") or lio.get("latest_release_published_at")
    stale_days = _days_since(last_update)
    lio_status = (lio.get("status") or "").lower()
    deprecated = bool(pkg.get("deprecated")) or lio_status in ("deprecated", "removed", "unmaintained")

    maintenance = _maintenance_status(stale_days, deprecated)
    out = {
        "package_name": pkg.get("name") or name, "ecosystem": eco,
        "version": pkg.get("version"),
        "license": pkg.get("license"),
        "known_vulnerabilities": None,  # not surfaced by these free sources directly
        "maintenance_status": maintenance,
        "last_update": last_update,
        "days_since_update": stale_days,
        "download_trends": {"npm_last_month": downloads} if downloads is not None else None,
        "dependents_count": lio.get("dependents_count"),
        "deprecated_status": deprecated,
        "deprecation_message": pkg.get("deprecation_message") or lio.get("deprecation_reason"),
        "release_count": pkg.get("release_count"),
        "libraries_io": lio if lio.get("available") else {"available": False},
    }
    out["risk_score"] = _risk_score(out, stale_days, deprecated, downloads, lio)
    return out


def _maintenance_status(stale_days: int | None, deprecated: bool) -> str:
    if deprecated:
        return "deprecated"
    if stale_days is None:
        return "unknown"
    if stale_days <= 90:
        return "active"
    if stale_days <= 365:
        return "slow"
    if stale_days <= 730:
        return "stale"
    return "abandoned"


def _risk_score(d: dict, stale_days: int | None, deprecated: bool,
                downloads: int | None, lio: dict) -> int:
    """0-100 where HIGHER = riskier."""
    risk = 0.0
    if deprecated:
        risk += 45
    # Staleness (max 35).
    if stale_days is None:
        risk += 15
    elif stale_days > 730:
        risk += 35
    elif stale_days > 365:
        risk += 22
    elif stale_days > 180:
        risk += 10
    elif stale_days > 90:
        risk += 4
    # Adoption — popular packages are lower risk (subtract up to 25).
    dependents = lio.get("dependents_count") or 0
    if dependents >= 10000 or (downloads or 0) >= 10_000_000:
        risk -= 25
    elif dependents >= 1000 or (downloads or 0) >= 1_000_000:
        risk -= 15
    elif dependents >= 100 or (downloads or 0) >= 100_000:
        risk -= 8
    # No license is a governance risk.
    if not d.get("license"):
        risk += 10
    return int(max(0, min(100, round(risk))))


# ── compare_packages ──────────────────────────────────────────────────────────
async def compare_packages(names: list, ecosystem: str) -> list:
    rows = []
    for n in names[:10]:
        r = await dependency_risk(n, ecosystem)
        if isinstance(r, dict) and r.get("error"):
            rows.append({"package_name": n, "ecosystem": ecosystem, "error": r.get("detail") or r.get("error")})
            continue
        rows.append({
            "package_name": r.get("package_name"), "ecosystem": r.get("ecosystem"),
            "version": r.get("version"), "license": r.get("license"),
            "downloads": (r.get("download_trends") or {}).get("npm_last_month") if r.get("download_trends") else None,
            "dependents_count": r.get("dependents_count"),
            "maintenance_status": r.get("maintenance_status"),
            "last_update": r.get("last_update"),
            "deprecated": r.get("deprecated_status"),
            "risk_score": r.get("risk_score"),
        })
    return rows
