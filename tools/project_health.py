from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def project_health(
        repo: str,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """Check open-source project health for a GitHub repository — stars, forks,
        open issues, commit frequency, last commit date, contributor count, license,
        and a 0-100 composite health_score (popularity + activity + maintenance +
        governance). The "is this project alive and worth depending on?" tool.
        Source: GitHub API.

        PAID: $0.01 USDC per query after a daily free allowance (25/day). On a 402,
        pay the returned Solana memo and re-call with the SAME args plus
        payment_tx=<signature>. agent_id scopes your allowance; an Authorization:
        Bearer fnet_ key bypasses it.

        Args:
            repo: GitHub repository as "owner/name", e.g. "facebook/react".
            agent_id: stable id for your agent (scopes the free-tier counter).
            payment_tx: Solana tx signature, when re-calling after a 402.
        """
        return await core.do_project_health(repo, agent_key=identity.resolve_agent_key(agent_id),
                                            payment_tx=payment_tx, api_key=identity.bearer())
