# Open Source Intelligence MCP

**Open source intelligence for AI agents** — GitHub project-health scoring,
package dependency-risk analysis, trending repositories, license checks, and
side-by-side package comparison.

> Part of the **FoundryNet Data Network**. Attest your agent's open-source
> analysis with [MINT Protocol](https://mint-mcp-production.up.railway.app/mcp).
> See also: **gov-contracts-mcp**, **cyber-intel-mcp**, **patent-intel-mcp**,
> **financial-signals-mcp**, **weather-intel-mcp**, **compliance-mcp**,
> **brand-intel-mcp**, **academic-intel-mcp**, **fact-check-mcp**, **social-intel-mcp**.

## Connect

- **MCP endpoint** (Streamable HTTP): `https://oss-intel-mcp-production.up.railway.app/mcp`
- **Registry:** `io.github.FoundryNet/oss-intel-mcp`
- **Agent card:** `https://oss-intel-mcp-production.up.railway.app/.well-known/agent-card.json`

### Claude Desktop / Cursor / Claude Code

```
claude mcp add --transport http oss-intel https://oss-intel-mcp-production.up.railway.app/mcp
```

```json
{ "mcpServers": { "oss-intel": { "url": "https://oss-intel-mcp-production.up.railway.app/mcp" } } }
```

## Tools

| Tool | Price | What it does |
|---|---|---|
| `project_health` | $0.01 | GitHub repo health — stars, forks, issues, commit frequency, contributors, license, **health_score (0-100)** |
| `dependency_risk` | $0.02 | Package risk — maintenance, last update, downloads, dependents, deprecation, **risk_score (0-100)** |
| `trending_repos` | $0.01 | Trending GitHub repositories with growth metrics |
| `license_check` | **free** | License type, permissions, restrictions, compatibility |
| `compare_packages` | $0.01 | Side-by-side: downloads, maintenance, dependents, risk_score |
| `daily_brief` | $5 | Curated daily brief: top trending, notable risks, newly deprecated, biggest growth |
| `mint_info` | **free** | FoundryNet Data Network + MINT Protocol |

**Free tier:** 25 paid-tool queries/day per agent. Then x402: the tool returns an
HTTP-402 with a Solana USDC payment memo — pay it, re-call with the same args plus
`payment_tx=<signature>`. An `Authorization: Bearer fnet_…` key bypasses the paywall.

## The edge: scored, not just listed

Raw stars and download counts are noise. Every repo carries a composite
**health_score** (popularity + activity + maintenance + governance) and every
package a **risk_score** (staleness + deprecation + adoption + license). An agent
triaging a dependency or picking between libraries sees what actually matters — is
this alive, maintained, and safe to depend on?

## Sources

Daily aggregation refreshes trending repos plus a watchlist of popular repos'
health and packages' risk. Live on demand: **GitHub API** (repos, contributors,
commits, search — keyless low-rate, optional `GITHUB_TOKEN` for higher limits),
**PyPI** + **npm registry** (package metadata + downloads), and **libraries.io**
(cross-ecosystem dependents/SourceRank/deprecation — optional `LIBRARIESIO_API_KEY`,
degrades gracefully if unset). Stored in a standalone Supabase project.

MCP registry: `io.github.FoundryNet/oss-intel-mcp`

Built by [FoundryNet](https://foundrynet.io) · hello@foundrynet.io

## Live network activity

**Live feed:** [mint.foundrynet.io/feed](https://mint.foundrynet.io/feed)  
Real-time verified work across 13 servers and autonomous agents, anchored on Solana via [MINT Protocol](https://mint.foundrynet.io).
