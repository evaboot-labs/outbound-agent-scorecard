"""Outbound agent scorecard. Your AI Agent runs four outbound steps on the same ten leads (find, qualify,
why now, first message); this script checks every output against the lead's real Evaboot data and scores
each step, so you know which step to hand to an agent first. Nothing here touches the network or sends.

    python3 scorecard.py facts data/export.json > runs/facts.json      the real fields per lead
    python3 scorecard.py check runs/facts.json runs/agent.json         every check, FAIL lines to fix
    python3 scorecard.py card runs/facts.json runs/agent.json > runs/scorecard.md
"""
import argparse
import json
import re
import sys

FIT = range(1, 6)            # 5 = exactly the ICP, 3 = worth a try, 1-2 = do not contact
FIT_MIN = 3                  # a lead at or above this gets a why-now and a message
EMAIL_WORDS = (40, 110)      # first email body
SUBJECT_MAX = 60             # characters
NOTE_MAX = 300               # LinkedIn connection note, characters
READY, ONE_RULE = 0.9, 0.6   # step verdicts: pass rate thresholds
# Phrases that make a message read like a template. Add your own.
CLICHES = ["hope this finds you", "i hope you're well", "just checking in", "quick question", "touch base",
           "circle back", "synergy", "game-changer", "game changer", "revolutionize", "i came across your profile",
           "happy to connect", "would love to connect", "pick your brain", "reaching out because"]
LINK_DOMAINS = {"ow.ly", "bit.ly", "linktr.ee", "lnkd.in", "beacons.ai", "carrd.co", "about.me", "t.co"}
LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|io|ai|co|net|org|app|dev|de)\b", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Fields a why-now may rest on: each is a change or a size that makes this month different.
SIGNALS = ["new_in_role", "months_in_role", "years_in_role", "company_growth_6m_pct", "company_growth_1y_pct",
           "sales_team", "employees"]
STEPS = [("find", "Find", "the export matches your filters"),
         ("qualify", "Qualify", "a fit score whose reason rests on real fields"),
         ("why_now", "Why now", "one real signal per fit lead"),
         ("write", "First message", "a draft that passes every message rule")]


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def clean(s, n=None):
    s = " ".join(str(s or "").split())
    if s in ("NA", "None", "N/A"):
        return ""
    return s[:n] if n else s


def domain_note(email, company_domain):
    """Empty when the email's domain is the company's; otherwise a reason to look before sending."""
    if not email:
        return ""
    domain, company = email.rsplit("@", 1)[-1].lower(), (company_domain or "").lower()
    if company in LINK_DOMAINS:
        return f"the company's domain is {company}, a link site: check the email by hand"
    if company and not (domain == company or domain.endswith("." + company) or company.endswith("." + domain)):
        return f"email domain {domain} differs from the company's {company}"
    return ""


def facts(path):
    """export.json = the Evaboot export (get_export, or the API). One entry per lead, real fields only."""
    out = []
    for p in json.load(open(path)).get("prospects") or []:
        years, mons = num(p.get("Years in Position")), num(p.get("Months in Position"))
        months = None if years is None and mons is None else int((years or 0) * 12 + (mons or 0))
        g6, g1 = num(p.get("Company Employee Growth 6 Months (%)")), num(p.get("Company Employee Growth 1 Year (%)"))
        out.append({
            "id": p.get("Linkedin URL Unique ID") or p.get("Linkedin URL Public") or p.get("Full Name"),
            "first_name": p.get("First Name") or "",
            "name": " ".join(x for x in [p.get("First Name"), p.get("Last Name")] if x),
            "matches_filters": p.get("Matches Filters") or "",
            "no_match_reasons": clean(p.get("No Match Reasons")),
            "title": clean(p.get("Current Job")),
            "company": p.get("Company Name") or "",
            "company_domain": p.get("Company Domain") or "",
            "industry": p.get("Company Industry") or "",
            "employees": num(p.get("Company Employee Exact Count")),
            "employee_range": p.get("Company Employee Range") or "",
            "company_growth_6m_pct": None if g6 is None else round(g6),
            "company_growth_1y_pct": None if g1 is None else round(g1),
            "sales_team": num(p.get("Sales Team Size")),
            "months_in_role": months,
            "years_in_role": None if months is None else months // 12,
            "new_in_role": str(p.get("Has New Position")).lower() in ("true", "yes", "1")
                           or (months is not None and months < 6),
            "location": p.get("Location") or p.get("Lead Location") or "",
            "headline": clean(p.get("Profile Headline")),
            "summary": clean(p.get("Profile Summary"), 600),
            "company_description": clean(p.get("Company Description"), 400),
            "email": p.get("Email") or "",
            "email_status": p.get("Email Status") or "not found",
            "email_check": domain_note(p.get("Email") or "", p.get("Company Domain")),
        })
    if not out:
        sys.exit(f"{path} has no prospects: check the curl response saved there")
    return out


def numbers_ok(text, lead, extra=""):
    """Every number in the text must come from the lead's facts (or the ICP): no invented figures."""
    known = set(NUMBER.findall(json.dumps(lead) + " " + extra))
    for v in lead.values():
        if isinstance(v, float) and v.is_integer():
            known.add(str(int(v)))
    return [n for n in NUMBER.findall(text or "") if n not in known and n.replace(",", "") not in known]


def present(v):
    return v is not None and v is not False and v not in ("", [])


def check_lead(lead, a, icp):
    """Returns {step: [problems]} for one lead; a step absent from the dict does not apply to this lead."""
    res = {"find": []}
    if lead["matches_filters"] and lead["matches_filters"] != "YES":
        res["find"].append(f"does not match the search filters ({lead['no_match_reasons'] or 'no reason given'})")
    if not a:
        res["qualify"] = ["the agent returned nothing for this lead"]
        return res
    q = res["qualify"] = []
    fit = a.get("fit") if isinstance(a.get("fit"), int) and a.get("fit") in FIT else 0
    if not fit:
        q.append("fit must be 1 to 5")
    if not clean(a.get("reason")):
        q.append("no reason")
    ev = a.get("evidence") or []
    if not ev:
        q.append("no evidence fields")
    for f in ev:
        if f not in lead:
            q.append(f"evidence field '{f}' does not exist")
        elif not present(lead[f]):
            q.append(f"evidence field '{f}' is empty for this lead")
    for n in numbers_ok(a.get("reason"), lead, icp):
        q.append(f"number {n} in the reason is not in the data")
    if lead["matches_filters"] and lead["matches_filters"] != "YES" and fit >= FIT_MIN:
        q.append("scored a fit although it does not match the search filters")
    if fit < FIT_MIN:
        if a.get("message"):
            q.append("a lead under the fit bar must not get a message")
        return res
    w = res["why_now"] = []
    field = a.get("why_now_field")
    if not clean(a.get("why_now")):
        w.append("no why-now line")
    if field not in SIGNALS:
        w.append(f"why_now_field must be one of {', '.join(SIGNALS)}")
    elif not present(lead.get(field)):
        w.append(f"'{field}' is empty for this lead: the signal is invented")
    for n in numbers_ok(a.get("why_now"), lead, icp):
        w.append(f"number {n} in the why-now is not in the data")
    m = res["write"] = []
    msg, ch = clean(a.get("message")), a.get("channel")
    if a.get("skip"):
        if not clean(a.get("skip_reason")):
            m.append("skipped without a reason")
        return res
    if ch not in ("email", "linkedin"):
        m.append("channel must be email or linkedin")
    if not msg:
        m.append("no message")
    if ch == "email":
        if lead["email_status"] != "safe":
            m.append(f"email channel but the email is {lead['email_status']}: use linkedin")
        if lead["email_check"]:
            m.append(lead["email_check"])
        words = len(msg.split())
        if not EMAIL_WORDS[0] <= words <= EMAIL_WORDS[1]:
            m.append(f"{words} words, keep {EMAIL_WORDS[0]} to {EMAIL_WORDS[1]}")
        subj = clean(a.get("subject"))
        if not subj or len(subj) > SUBJECT_MAX:
            m.append(f"subject missing or over {SUBJECT_MAX} characters")
    if ch == "linkedin" and len(msg) > NOTE_MAX:
        m.append(f"{len(msg)} characters, a connection note takes {NOTE_MAX}")
    low = (msg + " " + clean(a.get("subject"))).lower()
    m += [f"template phrase: '{c}'" for c in CLICHES if c in low]
    if LINK.search(msg):
        m.append("a link or a domain in a first message")
    if lead["first_name"] and lead["first_name"].lower() not in msg.lower():
        m.append(f"does not greet {lead['first_name']} by name")
    for n in numbers_ok(msg + " " + clean(a.get("subject")), lead, icp):
        m.append(f"number {n} is not in the data")
    if a.get("sent"):
        m.append("marked as sent: this agent never sends")
    return res


def run_checks(facts_path, agent_path):
    leads = json.load(open(facts_path))
    agent = json.load(open(agent_path))
    by_id = {a.get("id"): a for a in agent.get("leads") or []}
    icp = agent.get("icp") or ""
    unknown = [i for i in by_id if i not in {l["id"] for l in leads}]
    return leads, by_id, [(l, check_lead(l, by_id.get(l["id"]), icp)) for l in leads], unknown


def tally(results):
    out = {}
    for key, *_ in STEPS:
        done = [r[key] for _, r in results if key in r]
        out[key] = (sum(1 for p in done if not p), len(done))
    return out


def verdict(ok, total):
    if not total:
        return "not reached"
    rate = ok / total
    return "ready for an agent" if rate >= READY else "fix one rule, run again" if rate >= ONE_RULE else "keep a person on it"


def cmd_check(args):
    leads, _, results, unknown = run_checks(args.facts, args.agent)
    fails = 0
    for lead, r in results:
        for step, probs in r.items():
            for p in probs:
                fails += 1
                print(f"FAIL {step:8} {lead['first_name'] or lead['id']} ({lead['company']}): {p}")
    for i in unknown:
        fails += 1
        print(f"FAIL agent   unknown lead id {i}")
    for (key, label, _), (ok, total) in zip(STEPS, tally(results).values()):
        print(f"{label:14} {ok}/{total} passed")
    print("OK: every check passed" if not fails else f"{fails} problem(s)")
    sys.exit(1 if fails and args.strict else 0)


def cell(s):
    return clean(s).replace("|", "/")


def cmd_card(args):
    leads, by_id, results, _ = run_checks(args.facts, args.agent)
    t = tally(results)
    print("# Outbound agent scorecard\n")
    print(f"{len(leads)} leads, the same leads through every step. Nothing was sent.\n")
    print("| Step | What is checked | Passed | Verdict |\n|---|---|---|---|")
    for key, label, what in STEPS:
        ok, total = t[key]
        print(f"| {label} | {what} | {ok}/{total} | {verdict(ok, total)} |")
    first = next((label for key, label, _ in STEPS if t[key][1] and t[key][0] / t[key][1] >= READY), None)
    print(f"\n**Hand to an agent first:** {first or 'no step yet: fix the failing rule and run the ten leads again'}.\n")
    print("| Lead | Title | Company | Fit | Reason | Why now | Channel | Message | Problems |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lead, r in results:
        a = by_id.get(lead["id"]) or {}
        probs = "; ".join(f"{s}: {p}" for s, ps in r.items() for p in ps) or "none"
        msg = "skipped: " + clean(a.get("skip_reason")) if a.get("skip") else clean(a.get("message"))
        print(f"| {cell(lead['first_name'])} | {cell(lead['title'])} | {cell(lead['company'])} | {a.get('fit', '')} | "
              f"{cell(a.get('reason'))} | {cell(a.get('why_now'))} | {a.get('channel') or ''} | {cell(msg)} | {cell(probs)} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("facts")
    f.add_argument("export")
    for name in ("check", "card"):
        s = sub.add_parser(name)
        s.add_argument("facts")
        s.add_argument("agent")
        if name == "check":
            s.add_argument("--strict", action="store_true", help="exit 1 when any check fails")
    args = ap.parse_args()
    if args.cmd == "facts":
        json.dump(facts(args.export), sys.stdout, indent=2, ensure_ascii=False)
        print()
    elif args.cmd == "check":
        cmd_check(args)
    else:
        cmd_card(args)


if __name__ == "__main__":
    main()
