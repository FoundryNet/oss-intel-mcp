from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def dependency_risk(
        package_name: str,
        ecosystem: str,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Risk profile for a software package — maintenance status, last update,
        download trends, dependents, deprecation status, and a 0-100 risk_score
        (higher = riskier). The "should I add this dependency?" tool. Sources:
        PyPI/npm registry + libraries.io.

        PAID: $0.02 USDC per query after the daily free allowance (25/day). On a
        402, pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. An Authorization: Bearer fnet_ key bypasses it.

        Args:
            package_name: the package name, e.g. "express" or "requests".
            ecosystem: npm | pypi | cargo.
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_dependency_risk(package_name, ecosystem,
                                             agent_key=identity.resolve_agent_key(agent_id),
                                             payment_tx=payment_tx, api_key=identity.bearer())
