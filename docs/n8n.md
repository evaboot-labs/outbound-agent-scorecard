# Run it in n8n

[`n8n/outbound-agent-scorecard.json`](../n8n/outbound-agent-scorecard.json) is the same test for n8n: ten leads, four steps, one scorecard. You start it by hand.

## What runs

1. **Your settings** (Set): the Sales Navigator search URL, the export name, an optional `extraction_id`, and your ICP.
2. **Export 10 leads** (Evaboot MCP): skipped when you fill `extraction_id`, to rerun the same ten leads for free.
3. **Get the leads** and **Export done?** (Evaboot MCP + If): waits 30 seconds between checks until the export is finished, and stops with an error if it fails.
4. **Facts** (Code): the real fields of each lead, the same as `scorecard.py facts`.
5. **Run the agent** (AI Agent with Claude): fit, reason, evidence, why now and a first message per lead.
6. **Check and score** (Code): the same checks as `scorecard.py check`, and the scorecard as Markdown in `scorecard_md`.

## Set it up

1. **Import** the JSON: *Workflows > Import from file*.
2. **Add two credentials:**
   - **Bearer Auth** named `Evaboot MCP (Bearer)`: your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). Select it on **Export 10 leads** and **Get the leads**.
   - **Anthropic** on the **Claude** node.
3. **Fill in Your settings**, with your ICP from [ICP.md](../ICP.md).
4. **Run it:** *Execute workflow*. The first run spends 10 credits. Open **Check and score** to read the steps, the problems and the scorecard.
5. **Rerun after a fix:** copy the `extraction_id` from **Export 10 leads** into Your settings, change the ICP or the search, and run again on the same ten leads.

## Good to know

- Nothing is sent and nothing is written outside n8n.
- The checks live in one Code node. Add your own template phrases to `CLICHES` there and in `scorecard.py`.

Back to the [README](../README.md).
