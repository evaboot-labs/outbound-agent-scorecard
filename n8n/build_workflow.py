"""Builds n8n/outbound-agent-scorecard.json. Run: python3 n8n/build_workflow.py

Ten leads through four outbound steps: Evaboot exports a small Sales Navigator search, Claude qualifies each
lead, finds one why-now signal and drafts a first message, then a Code node checks every output against the
lead's real fields and scores each step. Nothing is sent.
"""
import json
import uuid
from pathlib import Path

EVABOOT_MCP = "https://mcp.evaboot.com/mcp"
EVABOOT_CRED = {"httpBearerAuth": {"id": "", "name": "Evaboot MCP (Bearer)"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
MODEL = "claude-sonnet-5-5"

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, kind="main", out=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": 0})


def mcp_call(name, tool, json_expr, pos):
    node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, {
        "endpointUrl": EVABOOT_MCP, "authentication": "bearerAuth",
        "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
        "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 120000},
    }, pos, EVABOOT_CRED)


def code(name, js, pos):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)


S = "$('Your settings').first().json"

FACTS_JS = r"""
// The real fields of each lead: the only facts the agent may use. Same as scorecard.py facts.
const r = $json.structuredContent?.result || {};
const num = v => { const n = parseFloat(String(v ?? '').replace(/[,%]/g, '')); return isNaN(n) ? null : n; };
const clean = (s, n) => { s = String(s ?? '').split(/\s+/).join(' ').trim(); if (['NA', 'None', 'N/A'].includes(s)) s = ''; return n ? s.slice(0, n) : s; };
const LINK_DOMAINS = ['ow.ly', 'bit.ly', 'linktr.ee', 'lnkd.in', 'beacons.ai', 'carrd.co', 'about.me', 't.co'];
const domainNote = (email, company) => {
  if (!email) return '';
  const d = email.split('@').pop().toLowerCase(); company = String(company || '').toLowerCase();
  if (LINK_DOMAINS.includes(company)) return `the company's domain is ${company}, a link site: check the email by hand`;
  if (company && !(d === company || d.endsWith('.' + company) || company.endsWith('.' + d))) return `email domain ${d} differs from the company's ${company}`;
  return '';
};
const leads = (r.prospects || []).slice(0, 10).map(p => {
  const y = num(p['Years in Position']), m = num(p['Months in Position']);
  const months = y === null && m === null ? null : Math.trunc((y || 0) * 12 + (m || 0));
  const g6 = num(p['Company Employee Growth 6 Months (%)']), g1 = num(p['Company Employee Growth 1 Year (%)']);
  return {
    id: p['Linkedin URL Unique ID'] || p['Linkedin URL Public'] || p['Full Name'],
    first_name: p['First Name'] || '', name: [p['First Name'], p['Last Name']].filter(Boolean).join(' '),
    matches_filters: p['Matches Filters'] || '', no_match_reasons: clean(p['No Match Reasons']),
    title: clean(p['Current Job']), company: p['Company Name'] || '', company_domain: p['Company Domain'] || '',
    industry: p['Company Industry'] || '', employees: num(p['Company Employee Exact Count']),
    employee_range: p['Company Employee Range'] || '',
    company_growth_6m_pct: g6 === null ? null : Math.round(g6), company_growth_1y_pct: g1 === null ? null : Math.round(g1),
    sales_team: num(p['Sales Team Size']), months_in_role: months, years_in_role: months === null ? null : Math.floor(months / 12),
    new_in_role: ['true', 'yes', '1'].includes(String(p['Has New Position']).toLowerCase()) || (months !== null && months < 6),
    location: p['Location'] || p['Lead Location'] || '', headline: clean(p['Profile Headline']),
    summary: clean(p['Profile Summary'], 600), company_description: clean(p['Company Description'], 400),
    email: p['Email'] || '', email_status: p['Email Status'] || 'not found',
    email_check: domainNote(p['Email'] || '', p['Company Domain']),
  };
});
if (!leads.length) throw new Error('The export has no leads.');
return [{ json: { leads } }];
"""

CHECK_JS = r"""
// Checks every output against the lead's real fields and scores each step. Same rules as scorecard.py.
const s = $('Your settings').first().json;
const leads = $('Facts').first().json.leads;
const out = Object.fromEntries(($json.output?.leads || []).map(a => [a.id, a]));
const FIT_MIN = 3, WORDS = [40, 110], SUBJECT_MAX = 60, NOTE_MAX = 300;
const CLICHES = ['hope this finds you', "i hope you're well", 'just checking in', 'quick question', 'touch base',
  'circle back', 'synergy', 'game-changer', 'game changer', 'revolutionize', 'i came across your profile',
  'happy to connect', 'would love to connect', 'pick your brain', 'reaching out because'];
const SIGNALS = ['new_in_role', 'months_in_role', 'years_in_role', 'company_growth_6m_pct', 'company_growth_1y_pct', 'sales_team', 'employees'];
const LINK = /https?:\/\/|www\.|\b[a-z0-9-]+\.(com|io|ai|co|net|org|app|dev|de)\b/i;
const NUM = /\d+(?:[.,]\d+)?/g;
const clean = x => String(x ?? '').split(/\s+/).join(' ').trim();
const present = v => !(v === null || v === undefined || v === '' || v === false || (Array.isArray(v) && !v.length));
const unknownNumbers = (text, lead) => {
  const known = new Set((JSON.stringify(lead) + ' ' + s.icp).match(NUM) || []);
  return (clean(text).match(NUM) || []).filter(n => !known.has(n) && !known.has(n.replace(/,/g, '')));
};
const results = leads.map(lead => {
  const a = out[lead.id], r = { find: [] };
  if (lead.matches_filters && lead.matches_filters !== 'YES') r.find.push(`does not match the search filters (${lead.no_match_reasons || 'no reason given'})`);
  if (!a) { r.qualify = ['the agent returned nothing for this lead']; return { lead, a: {}, r }; }
  const q = r.qualify = [];
  if (![1, 2, 3, 4, 5].includes(a.fit)) q.push('fit must be 1 to 5');
  if (!clean(a.reason)) q.push('no reason');
  if (!(a.evidence || []).length) q.push('no evidence fields');
  for (const f of a.evidence || []) {
    if (!(f in lead)) q.push(`evidence field '${f}' does not exist`);
    else if (!present(lead[f])) q.push(`evidence field '${f}' is empty for this lead`);
  }
  unknownNumbers(a.reason, lead).forEach(n => q.push(`number ${n} in the reason is not in the data`));
  if (lead.matches_filters && lead.matches_filters !== 'YES' && a.fit >= FIT_MIN) q.push('scored a fit although it does not match the search filters');
  if (!(a.fit >= FIT_MIN)) { if (a.message) q.push('a lead under the fit bar must not get a message'); return { lead, a, r }; }
  const w = r.why_now = [];
  if (!clean(a.why_now)) w.push('no why-now line');
  if (!SIGNALS.includes(a.why_now_field)) w.push(`why_now_field must be one of ${SIGNALS.join(', ')}`);
  else if (!present(lead[a.why_now_field])) w.push(`'${a.why_now_field}' is empty for this lead: the signal is invented`);
  unknownNumbers(a.why_now, lead).forEach(n => w.push(`number ${n} in the why-now is not in the data`));
  const m = r.write = [], msg = clean(a.message), subj = clean(a.subject);
  if (a.skip) { if (!clean(a.skip_reason)) m.push('skipped without a reason'); return { lead, a, r }; }
  if (!['email', 'linkedin'].includes(a.channel)) m.push('channel must be email or linkedin');
  if (!msg) m.push('no message');
  if (a.channel === 'email') {
    if (lead.email_status !== 'safe') m.push(`email channel but the email is ${lead.email_status}: use linkedin`);
    if (lead.email_check) m.push(lead.email_check);
    const n = msg.split(' ').filter(Boolean).length;
    if (n < WORDS[0] || n > WORDS[1]) m.push(`${n} words, keep ${WORDS[0]} to ${WORDS[1]}`);
    if (!subj || subj.length > SUBJECT_MAX) m.push(`subject missing or over ${SUBJECT_MAX} characters`);
  }
  if (a.channel === 'linkedin' && msg.length > NOTE_MAX) m.push(`${msg.length} characters, a connection note takes ${NOTE_MAX}`);
  const low = (msg + ' ' + subj).toLowerCase();
  CLICHES.filter(c => low.includes(c)).forEach(c => m.push(`template phrase: '${c}'`));
  if (LINK.test(msg)) m.push('a link or a domain in a first message');
  if (lead.first_name && !msg.toLowerCase().includes(lead.first_name.toLowerCase())) m.push(`does not greet ${lead.first_name} by name`);
  unknownNumbers(msg + ' ' + subj, lead).forEach(n => m.push(`number ${n} is not in the data`));
  return { lead, a, r };
});
const STEPS = [['find', 'Find', 'the export matches your filters'], ['qualify', 'Qualify', 'a fit score whose reason rests on real fields'],
  ['why_now', 'Why now', 'one real signal per fit lead'], ['write', 'First message', 'a draft that passes every message rule']];
const verdict = (ok, t) => !t ? 'not reached' : ok / t >= 0.9 ? 'ready for an agent' : ok / t >= 0.6 ? 'fix one rule, run again' : 'keep a person on it';
const steps = STEPS.map(([k, label, what]) => {
  const done = results.filter(x => k in x.r);
  const ok = done.filter(x => !x.r[k].length).length;
  return { step: label, checked: what, passed: ok, total: done.length, verdict: verdict(ok, done.length) };
});
const first = steps.find(x => x.total && x.passed / x.total >= 0.9);
const cell = x => clean(x).replace(/\|/g, '/');
const md = ['# Outbound agent scorecard', '', `${leads.length} leads, the same leads through every step. Nothing was sent.`, '',
  '| Step | What is checked | Passed | Verdict |', '|---|---|---|---|',
  ...steps.map(x => `| ${x.step} | ${x.checked} | ${x.passed}/${x.total} | ${x.verdict} |`), '',
  `**Hand to an agent first:** ${first ? first.step : 'no step yet: fix the failing rule and run the ten leads again'}.`, '',
  '| Lead | Title | Company | Fit | Reason | Why now | Channel | Message | Problems |', '|---|---|---|---|---|---|---|---|---|',
  ...results.map(({ lead, a, r }) => `| ${cell(lead.first_name)} | ${cell(lead.title)} | ${cell(lead.company)} | ${a.fit ?? ''} | ${cell(a.reason)} | ${cell(a.why_now)} | ${a.channel || ''} | ${cell(a.skip ? 'skipped: ' + a.skip_reason : a.message)} | ${cell(Object.entries(r).flatMap(([k, ps]) => ps.map(p => k + ': ' + p)).join('; ') || 'none')} |`)];
return [{ json: { steps, hand_first: first ? first.step : null,
  problems: results.flatMap(({ lead, r }) => Object.entries(r).flatMap(([k, ps]) => ps.map(p => `${k}: ${lead.first_name} (${lead.company}): ${p}`))),
  scorecard_md: md.join('\n') } }];
"""

AGENT_SYSTEM = """You are an outbound sales agent. You get an ICP and up to ten leads as JSON. For each lead, run three steps from that lead's fields and the ICP only. Never invent a customer, a number, a signal or a result.
1. Qualify: fit 1 to 5 by the ICP's fit rules, a one-line reason, and evidence: the names of the lead fields the reason rests on.
2. Why now (fit 3 or more): one line from one real signal, and why_now_field: one of new_in_role, months_in_role, years_in_role, company_growth_6m_pct, company_growth_1y_pct, sales_team, employees, which must be filled for this lead.
3. First message (fit 3 or more): channel "email" only when email_status is "safe" and email_check is empty, with a subject under 60 characters and a 40 to 110 word body; otherwise channel "linkedin", a connection note under 300 characters. Greet the lead by first name. One real fact, the offer in one line, the ask. No link, no template phrase. Or skip: true with a skip_reason.
Return {leads: [{id, fit, reason, evidence, why_now, why_now_field, channel, subject, message, skip, skip_reason}]}. Nothing is sent.

ICP:
"""

node("Start", "n8n-nodes-base.manualTrigger", 1, {}, [0, 0])
node("Your settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": "search_url", "type": "string", "value": "PASTE_A_SALES_NAVIGATOR_SEARCH_URL"},
    {"id": str(uuid.uuid4()), "name": "export_name", "type": "string", "value": "Outbound agent scorecard"},
    {"id": str(uuid.uuid4()), "name": "extraction_id", "type": "string", "value": ""},
    {"id": str(uuid.uuid4()), "name": "icp", "type": "string",
     "value": "PASTE YOUR ICP (see ICP.md): who, the fit rules, the offer, the proof you may use, the ask."},
]}, "options": {}}, [220, 0])
node("New export?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.extraction_id }}", "rightValue": "",
                    "operator": {"type": "string", "operation": "empty", "singleValue": True}}],
    "combinator": "and"}, "options": {}}, [440, 0])
mcp_call("Export 10 leads", "export_sn_search_or_list",
         "={{ JSON.stringify({ search_url: $json.search_url, name: $json.export_name, max_results: 10 }) }}", [660, -120])
mcp_call("Get the leads", "get_export",
         "={{ JSON.stringify({ extraction_id: " + S + ".extraction_id || $('Export 10 leads').first().json.structuredContent.result.extraction_id }) }}",
         [880, 0])
node("Export done?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.structuredContent?.result?.status }}",
                    "rightValue": "EXECUTED", "operator": {"type": "string", "operation": "equals"}}],
    "combinator": "and"}, "options": {}}, [1100, 0])
code("Still running?", r"""
// Stops on a failed export, or after 20 minutes, instead of waiting forever.
const st = String($json.structuredContent?.result?.status || '');
if (['FAILED', 'ERROR', 'CANCELLED', 'CANCELED'].includes(st.toUpperCase())) throw new Error(`The export ended as ${st}.`);
if ($runIndex >= 40) throw new Error('The export is still running after 20 minutes. Put its extraction_id in Your settings and run again later.');
return $input.all();
""", [1100, 360])
node("Wait 30 seconds", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [1100, 200], webhookId=str(uuid.uuid4()))
code("Facts", FACTS_JS, [1320, 0])
node("Run the agent", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "text": "={{ JSON.stringify($json.leads) }}", "hasOutputParser": True,
    "options": {"systemMessage": "=" + AGENT_SYSTEM + "{{ " + S + ".icp }}", "maxIterations": 3},
}, [1540, 0], retryOnFail=True, maxTries=3, waitBetweenTries=2000)
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 12000},
}, [1500, 220], ANTHROPIC_CRED)
node("Agent output", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["leads"], "properties": {"leads": {
        "type": "array", "items": {"type": "object", "required": ["id", "fit", "reason", "evidence"], "properties": {
            "id": {"type": "string"}, "fit": {"type": "integer"}, "reason": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}}, "why_now": {"type": "string"},
            "why_now_field": {"type": "string"}, "channel": {"type": "string"}, "subject": {"type": "string"},
            "message": {"type": "string"}, "skip": {"type": "boolean"}, "skip_reason": {"type": "string"}}}}}},
        indent=2),
}, [1660, 220])
code("Check and score", CHECK_JS, [1960, 0])

for a, b in [("Start", "Your settings"), ("Your settings", "New export?"), ("Export 10 leads", "Get the leads"),
             ("Get the leads", "Export done?"), ("Wait 30 seconds", "Get the leads"), ("Facts", "Run the agent"),
             ("Run the agent", "Check and score")]:
    link(a, b)
link("New export?", "Export 10 leads", out=0)
link("New export?", "Get the leads", out=1)
link("Export done?", "Facts", out=0)
link("Export done?", "Still running?", out=1)
link("Still running?", "Wait 30 seconds")
link("Claude", "Run the agent", "ai_languageModel")
link("Agent output", "Run the agent", "ai_outputParser")

workflow = {"name": "Outbound agent scorecard (Evaboot + Claude)", "nodes": nodes,
            "connections": connections, "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("outbound-agent-scorecard.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
