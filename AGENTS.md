# Agent instructions

This repo tests an AI outbound agent on ten real leads before anyone trusts it. Evaboot exports ten people from a Sales Navigator search. The agent runs four steps on the same leads: find, qualify, why now and first message. `scorecard.py` checks every output against the lead's real fields and scores each step, so the user knows which step to hand to an agent first. Nothing is sent.

1. Follow the skill in `skills/outbound-agent-scorecard/SKILL.md` step by step.
2. The ICP and the message rules are in `ICP.md`. If it says `Status: EXAMPLE`, ask the user for theirs and rewrite it.
3. If the Evaboot MCP tools are missing, follow `docs/connect-your-agent.md`.
4. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time.

Confirm with the user before every call that spends credits (1 Evaboot credit per lead): show the count first. Never send a message, never add a lead to an outreach tool: this repo only drafts. Never ask for or handle an API key: the user writes `EVABOOT_API_KEY` into `.env`. Never commit `.env`, `data/` or `runs/`: they hold real people's data and secrets.
