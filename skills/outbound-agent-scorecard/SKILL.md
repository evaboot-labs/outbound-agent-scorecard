---
name: outbound-agent-scorecard
description: Test an AI outbound sales agent on ten real leads before trusting it - turn an ICP into a Sales Navigator search, export ten leads with Evaboot, then qualify each lead from its real fields, find one why-now signal and draft a first message (email or LinkedIn note), check every output against the data with scorecard.py, and score each step to decide which one to hand to an agent first. Sends nothing. Use when the user asks which outbound step to automate first, wants to test an AI SDR or outbound agent on real leads, or asks for an AI agent for outbound sales.
---

# Outbound agent scorecard

This skill runs inside a clone of https://github.com/evaboot-labs/outbound-agent-scorecard: it uses the repo's `scorecard.py`, `ICP.md` and `docs/`. If `scorecard.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). You are the agent under test: you qualify, find the why-now and write the messages yourself. `scorecard.py` checks your work against the real data and scores each step.

## Rules

- **Nothing is sent.** You draft only. Never add a lead to an outreach tool or a CRM from this skill.
- Confirm with the user before `export_sn_search_or_list`: show the count and the cost (1 Evaboot credit per lead, 10 leads), then wait for a yes.
- Qualify and write only from that lead's entry in `runs/facts.json` and from `ICP.md`. Never invent a customer, a number, a signal or a result.
- Never ask for or paste an API key. The user writes `EVABOOT_API_KEY` into `.env`.
- Print every Sales Navigator URL as a Markdown link with the URL in angle brackets: `[Open in Sales Navigator](<url>)`.

## Step 0: check the setup

1. If the Evaboot MCP tools are missing, walk the user through `docs/connect-your-agent.md`, then ask them to restart the agent from this folder.
2. Call `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to sign in to Evaboot in Chrome, open any Sales Navigator search with the Evaboot extension, and click Export with Evaboot, then call it again.
3. Run `mkdir -p data runs`, and `cp .env.example .env` if `.env` is missing.
4. Read `ICP.md`. If it says `Status: EXAMPLE`, ask who they sell to, the fit rules, the offer, the proof they may use and the ask. Rewrite it and set `Status: yours`.

## Step 1: find (ten leads)

1. Call `build_sn_search_from_prompt` with **people only** (titles, seniority, geography) and `max_results: 10`. An industry or a company size in the prompt starts a slower company-first search.
2. Poll `get_search_build`. Add the industry and size filters to the URL yourself (`INDUSTRY`, `COMPANY_HEADCOUNT`), and narrow broad title keywords to the exact titles in the ICP. Show the URL as a link.
3. On a yes, call `export_sn_search_or_list` with `max_results: 10`. Poll `get_export` with `limit: 0` until `EXECUTED`.
4. Save the leads: `set -a; . ./.env; set +a; curl -s -H "Authorization: Bearer $EVABOOT_API_KEY" https://api.evaboot.com/v1/extractions/<extraction_id>/ > data/export.json`

```bash
python3 scorecard.py facts data/export.json > runs/facts.json
```

## Step 2: run the agent

Read `ICP.md`, then write `runs/agent.json`: `{"icp": "<the ICP in one paragraph>", "leads": [...]}`, one entry per lead in `facts.json`, all in one pass, the way an agent would run unattended.

- **Qualify**, every lead: `id`, `fit` (1 to 5 by the fit rules), `reason` (one line) and `evidence` (the names of the `facts.json` fields the reason rests on).
- **Why now**, fit 3 or more: `why_now` (one line) and `why_now_field`: one of `new_in_role`, `months_in_role`, `years_in_role`, `company_growth_6m_pct`, `company_growth_1y_pct`, `sales_team`, `employees`, filled for this lead.
- **First message**, fit 3 or more: `channel` `email` (when `email_status` is `safe` and `email_check` is empty, with `subject` and `message`) or `linkedin` (a connection note in `message`). Or `skip: true` with `skip_reason`.

Copy it to `runs/agent.first-pass.json` before any fix: the scorecard is about the first pass.

## Step 3: check and score

```bash
python3 scorecard.py check runs/facts.json runs/agent.first-pass.json
python3 scorecard.py card runs/facts.json runs/agent.first-pass.json > runs/scorecard.md
python3 claimcheck.py check runs/facts.json runs/agent.first-pass.json
```

`claimcheck.py` reads what each draft says about the lead. It fails a number used as the wrong field (21 written as the team size when 21 is the growth rate), "new role" when `new_in_role` is false, "growing" when both growth fields are negative, funding or a launch the data doesn't mention, the wrong function, and another lead's name or company. Show its `FAIL` lines with the scorecard's.

Show the step table and every `FAIL` line. Each step gets a verdict: **ready for an agent** (9 in 10 pass), **fix one rule, run again** (6 in 10), **keep a person on it** (under 6). The card names the step to hand to an agent first.

## Step 4: fix one rule

Pick the failing rule with the most hits, with the user. A **Find** failure is fixed in the search (titles, size), a **Qualify** or **Why now** failure in `ICP.md`, a **First message** failure in the message rules. Fix `runs/agent.json`, run `check` again until it prints `OK`, and show the drafts for the user to read. They copy what they like into their outreach tool themselves.

Next: run the same ten leads again after each rule change, and hand the step marked ready to an agent. To run it in n8n, follow `docs/n8n.md`.
