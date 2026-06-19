"""oss-intel-mcp tools — one per file.

  project_health    ($0.01)  GitHub repo health (stars/activity/contributors → score)
  dependency_risk   ($0.02)  package risk profile (PyPI/npm + libraries.io) + risk_score
  trending_repos    ($0.01)  trending GitHub repositories w/ growth metrics
  license_check     (free)   license type, permissions, restrictions, compatibility
  compare_packages  ($0.01)  side-by-side package comparison
  daily_brief       ($5)     curated daily open-source brief (premium, attested)
  mint_info         (free)   FoundryNet Data Network + MINT cross-promo
"""
from . import project_health as project_health_tool
from . import dependency_risk as dependency_risk_tool
from . import trending_repos as trending_repos_tool
from . import license_check as license_check_tool
from . import compare_packages as compare_packages_tool
from . import daily_brief as daily_brief_tool
from . import mint as mint_tool


def register_all(mcp) -> None:
    for m in (project_health_tool, dependency_risk_tool, trending_repos_tool,
              license_check_tool, compare_packages_tool, daily_brief_tool, mint_tool):
        m.register(mcp)
