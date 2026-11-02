# Connect your AI Agent

The scorecard needs one MCP server: Evaboot.

## 1. Account

An [Evaboot account](https://dash.evaboot.com/accounts/signup/?last_click_origin=outbound-agent-scorecard-repo) with at least 10 credits, and a Sales Navigator seat connected to it.

## 2. Get the repo

```bash
git clone https://github.com/evaboot-labs/outbound-agent-scorecard
cd outbound-agent-scorecard
cp .env.example .env
```

Write your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/) into `.env` as `EVABOOT_API_KEY`. `scorecard.py` needs only Python 3.

## 3. Connect the MCP server

**Claude Code:** start it from this folder. It reads `.mcp.json`, which takes the key from `.env` (export it first: `set -a; . ./.env; set +a`).

**Codex:** `codex mcp add evaboot --url https://mcp.evaboot.com/mcp --bearer-token-env-var EVABOOT_API_KEY`

**Cursor:** *Settings > MCP > Add new MCP server*, type HTTP, URL `https://mcp.evaboot.com/mcp`, header `Authorization: Bearer <your key>`.

**Claude or ChatGPT on the web:** add `https://mcp.evaboot.com/mcp` as a custom connector and sign in. The web apps cannot run `scorecard.py`, so use Claude Code, Codex or Cursor for this repo, or the n8n version.

## 4. Check

Ask your AI Agent: "Check my Evaboot quota and whether my Sales Navigator is connected." A quota and `has_valid_salesnav: true` mean you are ready.

Back to the [README](../README.md).
