"""Claim check for the drafts in runs/agent.json. scorecard.py makes sure every number in a draft is somewhere in the
lead's data. This script checks what the draft says about the lead: a number must match the field it is used as,
"new role" needs a new role, "growing" needs growth, and no other lead's name or company may show up in the draft.
Nothing here touches the network or sends.

    python3 claimcheck.py check runs/facts.json runs/agent.json     one FAIL line per claim the data does not back
"""
import argparse
import json
import re
import sys

FIELDS = ("reason", "why_now", "subject", "message")
NUMERIC = ("employees", "sales_team", "months_in_role", "years_in_role", "company_growth_6m_pct",
           "company_growth_1y_pct")
PROSE = ("title", "headline", "summary", "company_description", "industry", "location", "employee_range")
# Which fields a number may come from, by what the sentence says it counts.
FAMILY_FIELDS = {"growth": ("company_growth_6m_pct", "company_growth_1y_pct"), "months": ("months_in_role",),
                 "years": ("years_in_role",), "sales_team": ("sales_team",), "employees": ("employees",)}
FAMILY_LABEL = {"growth": "company growth", "months": "months in role", "years": "years in role",
                "sales_team": "sales team size", "employees": "employee count"}

NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*%|\s+percent\b)?", re.I)
# "in the last 6 months" names a window, not a fact about the lead.
WINDOW = re.compile(r"\b(?:in|over|during|across|for)\s+the\s+(?:last|past)\s+(?:6|12)\s+months\b"
                    r"|\b(?:last|past|this)\s+year\b", re.I)
HEDGE = re.compile(r"(?:about|around|roughly|nearly|almost|over|more than|close to|~)\s*$", re.I)
SALES_WORDS = {"sdr", "sdrs", "bdr", "bdrs", "rep", "reps", "seller", "sellers", "sales", "ae", "aes"}
HEAD_WORDS = {"employees", "people", "staff", "headcount", "company", "strong"}
DURATION_WORDS = {"minute", "minutes", "min", "mins", "hour", "hours", "day", "days", "week", "weeks"}

NEW_ROLE = re.compile(r"\bcongrat\w*\s+on\s+(?:the\s+|your\s+)?(?:new\s+|recent\s+)?(?:role|move|promotion|position|job)\b"
                      r"|\bnew\s+(?:role|position|job)\b|\bjust\s+(?:joined|started|stepped)\b"
                      r"|\brecently\s+(?:joined|started|took|moved|stepped)\b|\bstepp(?:ed|ing)\s+into\b"
                      r"|\bmoved\s+into\b|\bsettl\w*\s+into\b|\bfirst\s+(?:few\s+)?(?:weeks|months|90\s+days)\b", re.I)
GROW_VERB = re.compile(r"\b(?:grow|grows|growing|grown|grew|scale|scales|scaling|scaled|expand|expands|expanding|"
                       r"expanded|double|doubled|doubling|fast-growing|hypergrowth)\b", re.I)
SHRINK = re.compile(r"\b(?:shr[iu]nk\w*|downsiz\w*|layoffs?|laid\s+off|(?:down|fell|dropped|declined)\s+(?:by\s+)?\d+(?:\.\d+)?\s*%)", re.I)
# A growth verb after one of these is the sender talking about the offer ("help you grow pipeline"), not a claim.
OFFER_BEFORE = {"help", "helps", "to", "can", "will", "could", "would", "should", "you'll"}
OFFER_AFTER = {"pipeline", "revenue", "meetings", "replies", "bookings", "deals", "outbound", "your", "their"}
EVENT = re.compile(r"\b(?:raised|raising|funding|series\s+[a-e]|seed\s+round|ipo|acquired|acquisition|merger|hiring|"
                   r"open\s+roles?|job\s+(?:post|posting|ad)s?|launch(?:ed|es|ing)?|announc\w+|award\w*|podcast|"
                   r"(?:new|opened|opening)\s+(?:an?\s+|the\s+)?(?:[A-Z]\w+\s+)?offices?|webinar|conference|keynote|your\s+(?:recent\s+)?(?:post|article|talk)|you\s+(?:posted|wrote|shared|spoke))\b", re.I)
FUNCTIONS = {"sales": ("sales", "sdr", "bdr", "business development", "revenue", "outbound", "commercial"),
             "marketing": ("marketing", "demand gen", "brand"),
             "engineering": ("engineering", "developer"),
             "finance": ("finance", "accounting"),
             "customer success": ("customer success", "support"),
             "people": ("hr", "people", "talent", "recruiting"),
             "product": ("product",)}
FUNC_WORDS = r"(marketing|demand gen|engineering|finance|accounting|customer success|support|hr|people|talent|" \
             r"recruiting|product|sales|sdr|bdr|revenue)"
ROLE_CLAIM = re.compile(rf"\b(?:your|(?:lead|leads|leading|run|runs|running|manage|manages|managing|head|heads|heading)"
                        rf"\s+(?:the\s+|a\s+)?)\s*{FUNC_WORDS}\s+(?:team|org|organisation|organization|function|department)\b"
                        rf"|\b(?:head\s+of|vp\s+of|director\s+of|leading|running|heading|managing)\s+{FUNC_WORDS}\b", re.I)
LEGAL = re.compile(r"\s+(?:GmbH|AG|SE|KG|Ltd\.?|Inc\.?|SAS|BV|LLC)$")


def to_num(s):
    return float(s.replace(",", ""))


def numbers_in(text):
    return {to_num(m.group(1)) for m in NUM.finditer(text or "")}


def prose_of(lead):
    return " ".join(str(lead.get(f) or "") for f in PROSE)


def family(text, start, end, pct):
    """What a number counts, read from the words around it; None when the sentence does not say."""
    if pct:
        return "growth"
    words = re.findall(r"[a-z]+", text[end:end + 30].lower())[:3]
    before = text[max(0, start - 30):start].lower()
    if words and words[0].startswith("month"):
        return "months"
    if words and words[0] in ("year", "years", "yr", "yrs"):
        return "years"
    if words and words[0] in DURATION_WORDS:
        return None
    if SALES_WORDS & set(words) or re.search(r"(?:sales|sdr|bdr)\s+team\s+(?:of|to|at)\s*$", before):
        return "sales_team"
    if HEAD_WORDS & set(words):
        return "employees"
    if re.search(r"(?:headcount|employees|staff)\s+(?:of|at|is|to|near)\s*$", before):
        return "employees"
    if re.search(r"(?:team|sdrs|reps)\s+(?:of|to|at)\s*$", before):
        return "sales_team"
    if re.search(r"(?:grew|growth|grown|up|down)\s+(?:by\s+|of\s+)?$", before):
        return "growth"
    return None


def range_bounds(lead):
    return [to_num(x) for x in re.findall(r"\d[\d,]*", str(lead.get("employee_range") or ""))]


def fits(n, fam, lead, hedged):
    vals = [lead.get(f) for f in FAMILY_FIELDS[fam] if lead.get(f) is not None]
    if fam == "growth":
        return any(abs(n) == abs(v) for v in vals)
    if fam == "years" and lead.get("months_in_role") is not None:
        m = lead["months_in_role"]
        vals += [m // 12, round(m / 12)]
    if any(n == v for v in vals):
        return True
    if fam == "employees" and hedged:
        lo_hi = range_bounds(lead)
        return any(abs(n - v) <= 0.1 * v for v in vals) or (len(lo_hi) == 2 and lo_hi[0] - 1 <= n <= lo_hi[1])
    return False


def show(lead, fields):
    return ", ".join(f"{f} is {'empty' if lead.get(f) is None else fmt(lead[f])}" for f in fields)


def fmt(v):
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def check_numbers(text, lead, icp_numbers):
    out, scan = [], WINDOW.sub(lambda m: " " * len(m.group()), text)
    prose_nums = numbers_in(prose_of(lead)) | set(range_bounds(lead))
    known = {abs(lead[f]) for f in NUMERIC if lead.get(f) is not None}
    for m in NUM.finditer(scan):
        n, fam = to_num(m.group(1)), family(scan, m.start(), m.end(), bool(m.group(2)))
        shown = m.group(0).strip()
        if fam is None:
            if n not in known and n not in prose_nums and n not in icp_numbers:
                out.append(("unsupported", "invented_number", f"{shown} is not in the lead's data"))
            continue
        if fits(n, fam, lead, bool(HEDGE.search(scan[:m.start()]))):
            continue
        label, own = FAMILY_LABEL[fam], FAMILY_FIELDS[fam]
        others = [f for f in NUMERIC if f not in own and lead.get(f) is not None and abs(lead[f]) == n]
        if others:
            out.append(("contradicted", "misattributed_number",
                        f"{shown} is used as the {label}, but {fmt(n)} is {others[0]}; {show(lead, own)}"))
        elif n in prose_nums:
            out.append(("unsupported", "number_from_text",
                        f"{shown} is used as the {label}, but it only appears in the profile text; {show(lead, own)}"))
        else:
            out.append(("unsupported", "invented_number", f"{shown} is used as the {label}; {show(lead, own)}"))
    return out


def growth_values(lead):
    return [lead[f] for f in FAMILY_FIELDS["growth"] if lead.get(f) is not None]


def growth_claims(text):
    """Growth verbs that describe the lead's company, not the sender's offer."""
    hits = []
    for m in GROW_VERB.finditer(text):
        before = re.findall(r"[\w']+", text[max(0, m.start() - 30):m.start()].lower())[-3:]
        after = re.findall(r"[\w']+", text[m.end():m.end() + 20].lower())[:1]
        if OFFER_BEFORE & set(before) or (after and after[0] in OFFER_AFTER):
            continue
        hits.append(m.group(0))
    return hits


def check_claims(text, lead, others):
    out, prose = [], prose_of(lead).lower()
    m = NEW_ROLE.search(text)
    if m and not lead.get("new_in_role"):
        if lead.get("months_in_role") is None:
            out.append(("unsupported", "false_new_role", f"'{m.group(0)}': the data has no start date"))
        else:
            out.append(("contradicted", "false_new_role",
                        f"'{m.group(0)}': {lead['months_in_role']} months in role, new_in_role is false"))
    grow, g = growth_claims(text), growth_values(lead)
    if grow:
        if not g:
            out.append(("unsupported", "growth_claim_no_data", f"'{grow[0]}': the data has no growth figure"))
        elif max(g) <= 0:
            out.append(("contradicted", "wrong_growth_direction",
                        f"'{grow[0]}': {show(lead, FAMILY_FIELDS['growth'])}"))
    s = SHRINK.search(text)
    if s and g and min(g) >= 0:
        out.append(("contradicted", "wrong_growth_direction", f"'{s.group(0)}': {show(lead, FAMILY_FIELDS['growth'])}"))
    for e in EVENT.finditer(text):
        word = e.group(0).lower()
        if word in prose or (word == "hiring" and g and max(g) > 0):
            continue
        out.append(("unsupported", "unsupported_event", f"'{e.group(0)}': no field in the export says this"))
        break
    title = f"{lead.get('title') or ''} {lead.get('headline') or ''}".lower()
    for r in ROLE_CLAIM.finditer(text):
        word = (r.group(1) or r.group(2)).lower()
        func = next(f for f, words in FUNCTIONS.items() if word in words or word == f)
        if not any(w in title for w in FUNCTIONS[func]):
            out.append(("contradicted", "wrong_function", f"'{r.group(0)}': the title is {lead.get('title')}"))
            break
    for name in others:
        if name.lower() in prose or name.lower() in (lead.get("company") or "").lower():
            continue
        if re.search(rf"\b{re.escape(name)}\b", text):
            out.append(("contradicted", "cross_lead_leak", f"'{name}' belongs to another lead in this batch"))
            break
    return out


def batch_names(leads):
    """{lead id: names of every other lead and company}, to catch one lead's details landing in another's draft."""
    own = {}
    for l in leads:
        names = {LEGAL.sub("", l.get("company") or "").strip(), (l.get("company") or "").strip()}
        if len(l.get("first_name") or "") >= 3:
            names.add(l["first_name"])
        own[l["id"]] = {n for n in names if len(n) >= 3}
    return {i: set().union(*(v for j, v in own.items() if j != i)) - own[i] for i in own}


def check_agent(leads, agent):
    """[(lead, field, verdict, kind, detail)] for every draft field of every lead the agent answered."""
    by_id = {a.get("id"): a for a in agent.get("leads") or []}
    icp_numbers = numbers_in(agent.get("icp") or "")
    others = batch_names(leads)
    out = []
    for lead in leads:
        a = by_id.get(lead["id"])
        if not a:
            continue
        for field in FIELDS:
            text = " ".join(str(a.get(field) or "").split())
            if not text:
                continue
            for verdict, kind, detail in check_numbers(text, lead, icp_numbers) + check_claims(text, lead, others[lead["id"]]):
                out.append((lead, field, verdict, kind, detail))
    return out


def cmd_check(args):
    leads, agent = json.load(open(args.facts)), json.load(open(args.agent))
    findings = check_agent(leads, agent)
    for lead, field, verdict, kind, detail in findings:
        print(f"FAIL {field:8} {lead.get('first_name') or lead['id']} ({lead.get('company')}): {verdict} {kind}: {detail}")
    answered = {a.get("id") for a in agent.get("leads") or []}
    flagged = {f[0]["id"] for f in findings}
    print(f"{len(answered) - len(flagged)}/{len(answered)} drafts with every claim grounded")
    sys.exit(1 if findings and args.strict else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("facts")
    c.add_argument("agent")
    c.add_argument("--strict", action="store_true", help="exit 1 when any claim fails")
    cmd_check(ap.parse_args())


if __name__ == "__main__":
    main()
