from typing import List, Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def compare_packages(
        packages: List[str],
        ecosystem: str,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Compare open-source packages (npm or PyPI) side by side in one ecosystem —
        downloads, maintenance status, dependents (community size), deprecation,
        license, and risk_score. The "which of these should I pick?" tool. Sources:
        PyPI, npm registry, libraries.io.

        PAID: $0.01 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            packages: list of package names to compare (max 10).
            ecosystem: npm | pypi | cargo (applies to all packages).
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_compare_packages(packages, ecosystem,
                                              agent_key=identity.resolve_agent_key(agent_id),
                                              payment_tx=payment_tx, api_key=identity.bearer())
