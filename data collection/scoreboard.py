import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv; load_dotenv()
from supabase import create_client

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
WINDOW_DAYS, K = 30, 3          # K pulls scores toward 50 when articles are few
PILLARS = {"environmental": "e", "social": "s", "governance": "g"}

def label(v):
    return "Strong" if v >= 60 else "Weak" if v < 40 else "Average"

def pillar(impacts):
    n = len(impacts)
    score = 50 + (sum(impacts) / (n + K)) / 2          # impact -100..100 -> 0..100
    return {"score": round(score, 1), "n": n,
            "neg": sum(i < 0 for i in impacts), "neu": sum(i == 0 for i in impacts),
            "pos": sum(i > 0 for i in impacts)}

cut = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
rows = (sb.table("articles").select("company,aspect,impact_score")
        .not_.is_("impact_score", "null").gte("published_at", cut)
        .limit(10000).execute().data)

by = defaultdict(lambda: defaultdict(list))
for r in rows:
    by[r["company"]][PILLARS[r["aspect"]]].append(r["impact_score"])

out = []
for company, d in by.items():
    p = {k: pillar(d.get(k, [])) for k in "esg"}
    overall = round(sum(p[k]["score"] for k in "esg") / 3, 1)
    out.append({"company": company, **p, "overall": overall, "label": label(overall),
                "articles": sum(p[k]["n"] for k in "esg"),
                "updated_at": datetime.now(timezone.utc).isoformat()})
if out:
    sb.table("company_scores").upsert(out, on_conflict="company").execute()
print(f"scored {len(out)} companies from {len(rows)} articles")