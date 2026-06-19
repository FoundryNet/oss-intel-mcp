from typing import Optional

import core
import identity


def register(mcp) -> None:
    @mcp.tool
    async def license_check(
        repo: str,
        agent_id: Optional[str] = None,
        payment_tx: Optional[str] = None,
    ) -> dict:
        """License analysis for a GitHub repository — detected license type,
        permissions, restrictions, commercial-use eligibility, and compatibility
        guidance (permissive vs copyleft). FREE.

        Args:
            repo: GitHub repository as "owner/name", e.g. "facebook/react".
            agent_id: stable id for your agent (unused for free tools).
            payment_tx: unused (this tool is free).
        """
        return await core.do_license_check(repo, agent_key=identity.resolve_agent_key(agent_id),
                                           payment_tx=payment_tx, api_key=identity.bearer())
