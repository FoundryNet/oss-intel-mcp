from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def trending_repos(
        language: Optional[str] = None,
        topic: Optional[str] = None,
        period: Optional[str] = None,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Find trending GitHub repositories with growth metrics (stars, forks,
        language, license) — optionally filtered by language or topic. Unfiltered
        queries are served from the daily-aggregated snapshot; filtered ones hit
        GitHub search live. Source: GitHub API.

        PAID: $0.01 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            language: filter by primary language, e.g. "python", "rust".
            topic: filter by GitHub topic, e.g. "machine-learning".
            period: "daily" | "weekly" growth window (default weekly).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_trending_repos(language, topic, period,
                                            agent_key=identity.resolve_agent_key(agent_id),
                                            payment_tx=payment_tx, api_key=identity.bearer())
