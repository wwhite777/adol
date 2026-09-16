#!/usr/bin/env python3
"""S1 concurrent-work sweep (G2) — adol/KYRA-Bench, 2026-09-16.
Verifies plan-cited arXiv IDs against live metadata and runs dated neutral queries.
Zero successful requests -> exit 2 (a tool that processed nothing must say so)."""
import csv, os, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

BASE = "https://export.arxiv.org/api/query"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "2026-09-16")
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)
ATOM = "{http://www.w3.org/2005/Atom}"
UA = {"User-Agent": "adol-sweep/1.0 (research literature sweep)"}

# arXiv IDs exactly as plan v2/v1 cite them (verification targets, NOT trusted yet)
PLAN_IDS = {
    "KIDBench": "2605.25510", "SproutBench": "2508.11009", "CAREBench": "2606.29685",
    "CompanionBench": "2608.02046", "INTIMA": "2508.09998", "Cha_AIES26": "2608.07902",
    "ChildSafe": "2510.05484", "Safe-Child-LLM": "2506.13510", "MinorBench": "2503.10242",
    "YouthSafe": "2509.08997", "NeurIPS_construct_validity": "2511.04703",
}
# Works the plans cite WITHOUT an arXiv id -> title search, never a guessed id
TITLE_SEARCHES = {
    "RedQueen": 'ti:"Red Queen" AND cat:cs.CL',
    "XSTest": 'ti:"XSTest"',
    "HarmBench": 'ti:"HarmBench"',
}
# Neutral task-space queries (no pitch terms like CRRI/KYRA/practitioner-criterion)
QUERIES = {
    "child_safety_llm": 'all:"child safety" AND all:"language model"',
    "multiturn_safety_benchmark": 'all:"multi-turn" AND all:"safety" AND all:"benchmark"',
    "adolescent_chatbot_safety": 'all:"adolescent" AND all:"chatbot"',
    "ai_companion_risk": 'all:"AI companion" AND all:"risk"',
    "llm_judge_human_agreement": 'all:"LLM judge" AND all:"human" AND all:"agreement"',
    "overrefusal": 'all:"over-refusal" OR all:"exaggerated safety"',
    "korean_llm_safety": 'all:"Korean" AND all:"safety" AND all:"language model"',
    "grooming_conversational_ai": 'all:"grooming" AND all:"language model"',
    "emotional_dependence_chatbot": 'all:"emotional dependence" AND all:"chatbot"',
}
DATE_SORTED = ["child_safety_llm", "multiturn_safety_benchmark", "ai_companion_risk"]

ok_calls = fail_calls = 0
log_lines = [f"# Concurrent-work sweep — executed {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
             "Source: arXiv API (export.arxiv.org). Other G2 sources (OpenReview, PMLR, ACL Anthology, accepted lists) NOT queried this pass — recorded honestly; venue-status claims stay unverified where only arXiv was checked.", ""]

def fetch(name, params):
    global ok_calls, fail_calls
    url = BASE + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            data = r.read()
        with open(os.path.join(RAW, name + ".xml"), "wb") as f:
            f.write(data)
        ok_calls += 1
        log_lines.append(f"- {time.strftime('%H:%M:%SZ', time.gmtime())} OK   {name}: {urllib.parse.unquote(url)}")
        return ET.fromstring(data)
    except Exception as e:
        fail_calls += 1
        log_lines.append(f"- {time.strftime('%H:%M:%SZ', time.gmtime())} FAIL {name}: {e}")
        return None

def entries(feed):
    if feed is None: return []
    out = []
    for e in feed.findall(ATOM + "entry"):
        gid = e.findtext(ATOM + "id") or ""
        aid = gid.rsplit("/abs/", 1)[-1]
        title = " ".join((e.findtext(ATOM + "title") or "").split())
        if title == "Error" or aid.startswith("http"):  # arXiv error entry
            continue
        authors = [a.findtext(ATOM + "name") for a in e.findall(ATOM + "author")]
        out.append({
            "arxiv_id": aid, "title": title,
            "first_author": (authors[0] if authors else ""), "n_authors": len(authors),
            "published": (e.findtext(ATOM + "published") or "")[:10],
            "updated": (e.findtext(ATOM + "updated") or "")[:10],
            "abstract_head": " ".join((e.findtext(ATOM + "summary") or "").split())[:300],
        })
    return out

# 1) batched ID verification
feed = fetch("id_verification", {"id_list": ",".join(PLAN_IDS.values()), "max_results": len(PLAN_IDS)})
got = {e["arxiv_id"].split("v")[0]: e for e in entries(feed)}
with open(os.path.join(OUT, "id_verification.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["plan_name", "plan_cited_id", "resolved", "title", "first_author", "n_authors", "published", "updated", "abstract_head"])
    for name, pid in PLAN_IDS.items():
        e = got.get(pid)
        if e: w.writerow([name, pid, "YES", e["title"], e["first_author"], e["n_authors"], e["published"], e["updated"], e["abstract_head"]])
        else: w.writerow([name, pid, "NO_MATCH", "", "", "", "", "", ""])
time.sleep(3)

# 2) title searches for works cited without an arXiv id
rows = []
for name, q in TITLE_SEARCHES.items():
    feed = fetch("title_" + name, {"search_query": q, "max_results": 5})
    for i, e in enumerate(entries(feed), 1):
        rows.append([name, i, e["arxiv_id"], e["title"], e["first_author"], e["published"]])
    time.sleep(3)
with open(os.path.join(OUT, "title_search_results.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["target", "rank", "arxiv_id", "title", "first_author", "published"]); w.writerows(rows)

# 3) neutral queries — relevance for all, plus date-sorted for the core three
rows = []
for qname, q in QUERIES.items():
    for sort in (["relevance", "submittedDate"] if qname in DATE_SORTED else ["relevance"]):
        feed = fetch(f"q_{qname}_{sort}", {"search_query": q, "max_results": 20,
                                           "sortBy": sort, "sortOrder": "descending"})
        for i, e in enumerate(entries(feed), 1):
            rows.append([qname, sort, i, e["arxiv_id"], e["published"], e["title"], e["first_author"], e["abstract_head"]])
        time.sleep(3)
with open(os.path.join(OUT, "query_hits.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["query", "sort", "rank", "arxiv_id", "published", "title", "first_author", "abstract_head"]); w.writerows(rows)

log_lines += ["", f"Calls: {ok_calls} ok / {fail_calls} failed. Query hit rows: {len(rows)}."]
with open(os.path.join(OUT, "sweep_log.md"), "w") as f:
    f.write("\n".join(log_lines) + "\n")
print(f"ok={ok_calls} fail={fail_calls} hits={len(rows)} out={OUT}")
if ok_calls == 0:
    print("ZERO successful requests — sweep did not run.", file=sys.stderr); sys.exit(2)
