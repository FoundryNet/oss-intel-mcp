"""Env-driven configuration for oss-intel-mcp.

Open Source Intelligence: project health (GitHub), dependency risk (PyPI/npm +
libraries.io), trending repositories, license checks, and package comparison, in
its own standalone Supabase project. 6 tools + free mint_info, x402 metered. Part
of the FoundryNet Data Network.

Required to be useful:
  SUPABASE_URL, SUPABASE_SERVICE_KEY   the standalone oss-intel project.
Optional:
  GITHUB_TOKEN         higher GitHub API rate limit (else keyless + throttled)
  LIBRARIESIO_API_KEY  libraries.io dependency metadata — tools degrade without it
  PORT, REQUEST_TIMEOUT
  X402_ENABLED, SOLANA_WALLET, PAYMENT_RECIPIENT, PAYMENT_VERIFY_RPC,
  PAYMENT_USDC_MINT, PAYMENT_EXPIRY_SECONDS
  FREE_TIER_DAILY      default 25
  PRICE_*              per-tool USDC prices
"""
from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _flag(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


SUPABASE_URL         = _env("SUPABASE_URL", "https://keopysejsscdcjxyylvn.supabase.co").rstrip("/")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")

PORT            = int(_env("PORT", "8080"))
REQUEST_TIMEOUT = int(_env("REQUEST_TIMEOUT", "30"))

# ── Sources (all free / low-key) ─────────────────────────────────────────────
GITHUB_API        = "https://api.github.com"
GITHUB_TOKEN      = _env("GITHUB_TOKEN")
PYPI_API          = "https://pypi.org/pypi"          # /<pkg>/json
NPM_API           = "https://registry.npmjs.org"     # /<pkg>
NPM_DOWNLOADS_API = "https://api.npmjs.org/downloads" # /point/<period>/<pkg>
LIBRARIESIO_API   = "https://libraries.io/api"
LIBRARIESIO_API_KEY = _env("LIBRARIESIO_API_KEY")
SOURCE_USER_AGENT = _env("SOURCE_USER_AGENT", "FoundryNet Data Network hello@foundrynet.io")

# Watchlist of popular packages the aggregator refreshes daily (health/risk).
WATCHLIST_REPOS = [
    "facebook/react", "vuejs/vue", "angular/angular", "nodejs/node",
    "python/cpython", "rust-lang/rust", "golang/go", "torvalds/linux",
    "tensorflow/tensorflow", "pytorch/pytorch", "kubernetes/kubernetes",
    "django/django", "pallets/flask", "expressjs/express",
]
WATCHLIST_PACKAGES = [
    {"name": "react", "ecosystem": "npm"}, {"name": "express", "ecosystem": "npm"},
    {"name": "lodash", "ecosystem": "npm"}, {"name": "axios", "ecosystem": "npm"},
    {"name": "requests", "ecosystem": "pypi"}, {"name": "django", "ecosystem": "pypi"},
    {"name": "flask", "ecosystem": "pypi"}, {"name": "numpy", "ecosystem": "pypi"},
]

# ── x402 per-tool pricing ────────────────────────────────────────────────────
X402_ENABLED      = _flag("X402_ENABLED", True)
SOLANA_WALLET     = _env("SOLANA_WALLET", "wUumjWWvtFEr69qkTw3wHNVQVxLA8DTyJSyVgGmLThd")
PAYMENT_RECIPIENT = _env("PAYMENT_RECIPIENT", SOLANA_WALLET).strip()
PAYMENT_VERIFY_RPC = _env("PAYMENT_VERIFY_RPC", "https://api.mainnet-beta.solana.com").rstrip("/")
PAYMENT_USDC_MINT  = _env("PAYMENT_USDC_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v").strip()
PAYMENT_EXPIRY_SECONDS = int(_env("PAYMENT_EXPIRY_SECONDS", "300"))

FREE_TIER_DAILY = int(_env("FREE_TIER_DAILY", "25"))

PRICE_PROJECT_HEALTH   = float(_env("PRICE_PROJECT_HEALTH", "0.01"))
PRICE_DEPENDENCY_RISK  = float(_env("PRICE_DEPENDENCY_RISK", "0.02"))
PRICE_TRENDING_REPOS   = float(_env("PRICE_TRENDING_REPOS", "0.01"))
PRICE_LICENSE_CHECK    = float(_env("PRICE_LICENSE_CHECK", "0"))
PRICE_COMPARE_PACKAGES = float(_env("PRICE_COMPARE_PACKAGES", "0.01"))
PRICE_DAILY_BRIEF      = float(_env("PRICE_DAILY_BRIEF", "5"))

# Per-tool price table (mirrors the prompt's TOOL_PRICES contract).
TOOL_PRICES = {
    "project_health":   PRICE_PROJECT_HEALTH,
    "dependency_risk":  PRICE_DEPENDENCY_RISK,
    "trending_repos":   PRICE_TRENDING_REPOS,
    "license_check":    PRICE_LICENSE_CHECK,
    "compare_packages": PRICE_COMPARE_PACKAGES,
    "daily_brief":      PRICE_DAILY_BRIEF,
}


def _price_for(tool: str) -> float:
    return float(TOOL_PRICES.get(tool, 0) or 0)


# ── Daily curated brief ──────────────────────────────────────────────────────
BRIEF_HOUR_UTC = int(_env("BRIEF_HOUR_UTC", "5"))   # curator runs at 05:00 UTC
SERVER_SLUG    = "oss-intel"
# Cross-network brief catalog (server -> price + tool) for related_briefs.
NETWORK_BRIEFS = {
    "financial-signals": "$25", "cyber-intel": "$15", "patent-intel": "$10",
    "gov-contracts": "$10", "compliance": "$10", "brand-intel": "$5", "weather-intel": "$5",
    "fact-check": "$5", "oss-intel": "$5", "social-intel": "$5",
}

# ── FoundryNet Data Network cross-promo ──────────────────────────────────────
MINT_MCP_URL  = _env("MINT_MCP_URL", "https://mint-mcp-production.up.railway.app/mcp")
MINT_INFO_URL = _env("MINT_INFO_URL", "https://mint.foundrynet.io")
SISTER_SERVERS = {
    "mint-mcp":                "https://mint-mcp-production.up.railway.app/mcp",
    "foundrynet-mcp":          "https://foundrynet-mcp-production.up.railway.app/mcp",
    "gov-contracts-mcp":       "https://gov-contracts-mcp-production.up.railway.app/mcp",
    "brand-intel-mcp":         "https://brand-intel-mcp-production.up.railway.app/mcp",
    "patent-intel-mcp":        "https://patent-intel-mcp-production.up.railway.app/mcp",
    "financial-signals-mcp":   "https://financial-signals-mcp-production.up.railway.app/mcp",
    "weather-intel-mcp":       "https://weather-intel-mcp-production.up.railway.app/mcp",
    "cyber-intel-mcp":         "https://cyber-intel-mcp-production.up.railway.app/mcp",
    "compliance-mcp":          "https://compliance-mcp-production.up.railway.app/mcp",
    "academic-intel-mcp":      "https://academic-intel-mcp-production.up.railway.app/mcp",
    "fact-check-mcp":          "https://fact-check-mcp-production.up.railway.app/mcp",
    "social-intel-mcp":        "https://social-intel-mcp-production.up.railway.app/mcp",
    "crypto-intel-mcp":        "https://crypto-intel-mcp-production.up.railway.app/mcp",
    "market-data-mcp":         "https://market-data-mcp-production.up.railway.app/mcp",
    "email-verify-mcp":        "https://email-verify-mcp-production.up.railway.app/mcp",
    "currency-intel-mcp":      "https://currency-intel-mcp-production.up.railway.app/mcp",
}

PUBLIC_MCP_URL = _env("PUBLIC_MCP_URL", "https://oss-intel-mcp-production.up.railway.app/mcp")
