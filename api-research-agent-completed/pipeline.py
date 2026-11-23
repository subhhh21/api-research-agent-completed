"""Research agent (Free DuckDuckGo Web Search + Groq): python pipeline.py pass1 | pass2 | sample | analyze | bundle | one "Stripe" """
import json, os, sys, csv, random, time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict

MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
R = "results"
FIELDS = ["auth_primary", "access", "mcp", "verdict"]

SCHEMA = """Return ONE valid JSON object, nothing else (no markdown backticks):
{"what_it_does": "one line",
 "auth": ["OAuth2"|"API key"|"Basic"|"Bearer token"|"Other"],
 "auth_primary": "the auth a new developer would actually use first (same vocabulary as auth)",
 "access": "self-serve" (free signup or free trial gives credentials) | "paid" (needs paid plan) | "gated" (admin approval, app review, partnership or contact-sales),
 "access_detail": "one sentence",
 "api": "REST"|"GraphQL"|"REST+GraphQL"|"none",
 "api_breadth": "broad"|"medium"|"narrow"|"none",
 "mcp": "official"|"community"|"none",
 "verdict": "yes" (agent toolkit buildable today) | "partial" | "no",
 "blocker": "none"|"paid plan"|"partner approval"|"contact sales"|"app review"|"no public API"|"admin approval"|"other",
 "evidence": ["docs URLs from the search results"],
 "confidence": 0.0-1.0,
 "notes": "uncertainties; say so if you could not verify"}
Only state what you found in the search results. If you could not verify a field, say so in notes and lower confidence."""

def web_lookup(app_name):
    from ddgs import DDGS
    queries = [
        f"{app_name} developer API documentation authentication OAuth API key",
        f"{app_name} API pricing free self-serve gated partner",
        f"{app_name} MCP server official github"
    ]
    snippets, urls = [], []
    with DDGS() as ddgs:
        for q in queries:
            try:
                for r in ddgs.text(q, max_results=3):
                    urls.append(r.get("href", ""))
                    snippets.append(f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}")
            except Exception:
                pass
    return "\n---\n".join(snippets[:8]), list(dict.fromkeys([u for u in urls if u]))[:5]

def call(prompt, app_name):
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set!")
    search_context, urls = web_lookup(app_name)
    full_prompt = f"{prompt}\n\nWEB SEARCH RESULTS FOR {app_name}:\n{search_context}"
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.1,
        response_format={"type": "json_object"}
    )
    text = resp.choices[0].message.content or "{}"
    data = json.loads(text)
    if not data.get("evidence") and urls:
        data["evidence"] = urls
    return data

def research(app, prior=None):
    if prior is None:
        p = f"Research the app '{app['name']}' (category: {app['category']}) for building an AI-agent toolkit using the search results.\n{SCHEMA}"
    else:
        p = (f"A first-pass agent researched '{app['name']}'. Re-check EVERY field against the search results "
             f"(verify free vs paid access, primary auth, and whether MCP server is official or community).\n"
             f"First pass: {json.dumps(prior)}\nReturn the corrected object in this schema plus a 'changes' list of fields you changed and why.\n{SCHEMA}")
    err = "unknown"
    for attempt in range(3):
        try:
            res = call(p, app["name"])
            time.sleep(1.5)
            return {**app, **res}
        except Exception as e:
            err = str(e)[:200]
            time.sleep(5 * (attempt + 1))
    return {**app, "error": err, "confidence": 0}

def run(name, prior_file=None):
    os.makedirs(R, exist_ok=True)
    apps = json.load(open("apps.json", encoding="utf-8"))
    prior = {r["id"]: r for r in json.load(open(f"{R}/{prior_file}.json", encoding="utf-8"))} if prior_file else {}
    out_f = f"{R}/{name}.json"
    done = {r["id"]: r for r in json.load(open(out_f, encoding="utf-8"))} if os.path.exists(out_f) else {}
    todo = [a for a in apps if a["id"] not in done or "error" in done[a["id"]]]
    print(f"Running {name}: {len(todo)} remaining out of {len(apps)} apps...")
    with ThreadPoolExecutor(3) as ex:
        for row in ex.map(lambda a: research(a, prior.get(a["id"])), todo):
            done[row["id"]] = row
            json.dump(sorted(done.values(), key=lambda r: r["id"]), open(out_f, "w", encoding="utf-8"), indent=1)
            print(row["id"], row["name"], row.get("verdict", row.get("error")))

def sample():
    rows = json.load(open(f"{R}/pass1.json", encoding="utf-8"))
    p2 = {r["id"]: r for r in json.load(open(f"{R}/pass2.json", encoding="utf-8"))} if os.path.exists(f"{R}/pass2.json") else {}
    random.seed(7)
    by = defaultdict(list)
    for r in rows: by[r["category"]].append(r)
    pick = [x for c in by.values() for x in random.sample(c, min(3, len(c)))]
    with open(f"{R}/sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name"] + ["h_" + k for k in FIELDS] + ["human_notes", "docs_url_used"] +
                   [f"p1_{k}" for k in FIELDS] + [f"p2_{k}" for k in FIELDS])
        for r in pick:
            q = p2.get(r["id"], {})
            w.writerow([r["id"], r["name"]] + [""] * 6 + [r.get(k, "") for k in FIELDS] + [q.get(k, "") for k in FIELDS])
    print(f"Wrote {len(pick)} rows to {R}/sample.csv. Fill the h_* columns from REAL docs first, then run analyze.")

def analyze():
    p1 = {r["id"]: r for r in json.load(open(f"{R}/pass1.json", encoding="utf-8"))}
    p2 = {r["id"]: r for r in json.load(open(f"{R}/pass2.json", encoding="utf-8"))} if os.path.exists(f"{R}/pass2.json") else {}
    final = [p2.get(i, r) for i, r in p1.items()]
    ok = [r for r in final if "error" not in r]
    n = len(ok); pct = lambda x, t=None: f"{round(100 * x / (t or n))}%" if (t or n) else "0%"
    auth_any = Counter(a for r in ok for a in r.get("auth", []))
    prim = Counter(r.get("auth_primary") for r in ok)
    acc = Counter(r.get("access") for r in ok)
    blk = Counter(r.get("blocker") for r in ok if r.get("blocker") not in (None, "none"))
    mcp = Counter(r.get("mcp") for r in ok)
    cat = defaultdict(Counter)
    for r in ok: cat[r["category"]][r.get("access")] += 1
    easy = [r["name"] for r in ok if r.get("verdict") == "yes" and r.get("access") == "self-serve"]
    outreach = [r["name"] for r in ok if r.get("access") == "gated" or r.get("blocker") in ("partner approval", "contact sales")]
    gated_cat = max(cat, key=lambda c: (cat[c]["gated"] + cat[c]["paid"]) / sum(cat[c].values())) if cat else "-"
    patterns = [
        f"{prim.most_common(1)[0][0]} is the first-choice auth for {pct(prim.most_common(1)[0][1])} of apps; OAuth2 is offered by {pct(auth_any['OAuth2'])}.",
        f"{pct(acc['self-serve'])} are self-serve, {pct(acc['paid'])} need a paid plan, {pct(acc['gated'])} are gated.",
        f"Most common blocker: {blk.most_common(1)[0][0] if blk else 'none'} ({sum(blk.values())} apps have a blocker).",
        f"{len(easy)} easy wins (buildable today and self-serve); {len(outreach)} need outreach or approval.",
        f"Most paid/gated category: {gated_cat}. MCP already exists (official or community) for {pct(mcp['official'] + mcp['community'])}.",
    ]
    accuracy, misses = None, []
    sf = f"{R}/sample.csv"
    if os.path.exists(sf):
        hs = [r for r in csv.DictReader(open(sf, encoding="utf-8")) if all(r["h_" + k].strip() for k in FIELDS)]
        if hs:
            accuracy = {"n": len(hs), "fields": {}}
            for k in FIELDS:
                a1 = sum(r["p1_" + k].lower() == r["h_" + k].strip().lower() for r in hs)
                a2 = sum(r["p2_" + k].lower() == r["h_" + k].strip().lower() for r in hs) if p2 else None
                accuracy["fields"][k] = {"pass1": pct(a1, len(hs)), "pass2": pct(a2, len(hs)) if a2 is not None else "-"}
                for r in hs:
                    if r["p1_" + k].lower() != r["h_" + k].strip().lower():
                        misses.append({"app": r["name"], "field": k, "agent": r["p1_" + k], "after_verify": r["p2_" + k], "human": r["h_" + k]})
    notes = open("notes.md", encoding="utf-8").read() if os.path.exists("notes.md") else ""
    data = {"meta": {"model": MODEL, "apps": len(p1), "ok": n, "failed": len(p1) - n, "verified_pass": bool(p2)},
            "patterns": patterns, "auth": dict(auth_any), "access": dict(acc), "blockers": dict(blk),
            "easy": easy, "outreach": outreach, "accuracy": accuracy, "misses": misses, "notes": notes, "rows": final}
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(data))
    print("\n".join(patterns)); print("wrote data.js")

def bundle():
    d = open("data.js", encoding="utf-8").read().replace("</", "<\\/")
    h = open("index.html", encoding="utf-8").read().replace('<script src="data.js"></script>', "<script>" + d + "</script>")
    os.makedirs("dist", exist_ok=True)
    open("dist/index.html", "w", encoding="utf-8").write(h)
    print("wrote dist/index.html (single file, data inlined)")

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "pass1": run("pass1")
    elif cmd == "pass2": run("pass2", "pass1")
    elif cmd == "sample": sample()
    elif cmd == "analyze": analyze()
    elif cmd == "bundle": bundle()
    elif cmd == "one":
        print(json.dumps(research({"id": 0, "category": "?", "name": sys.argv[2]}), indent=1))