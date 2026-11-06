import os, time, hashlib, requests
from datetime import datetime, timezone
from urllib.parse import urlsplit
from supabase import create_client
import feedparser, urllib.parse
from dotenv import load_dotenv
import trafilatura
from concurrent.futures import ThreadPoolExecutor
from googlenewsdecoder import gnewsdecoder
from datetime import datetime, timezone, timedelta
load_dotenv()

MAX_FETCH, MAX_CHARS = 600, 2500   # per run cap, chars stored per article

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
HEADERS = UA

AI_GIANTS = ["NVIDIA","Microsoft","Google","Meta","OpenAI","Amazon","Anthropic",
             "Apple","Tesla","IBM","AMD","Oracle","Intel","Baidu","Alibaba"]
CAP = 150
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
ND_KEY = os.getenv("NEWSDATA_KEY")

def norm(url):
    p = urlsplit(url)
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}"

def make_id(company, url):
    return hashlib.md5(f"{company}|{norm(url)}".encode()).hexdigest()

def get_with_retry(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                wait = 10 * (i + 1)
                print(f"429, waiting {wait}s")
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.RequestException as e:
            print(f"retry {i+1}/{tries}: {e}")
            time.sleep(5 * (i + 1))
    return None

ESG_TERMS = ["emissions OR climate OR energy OR water",
             "layoffs OR union OR workers OR diversity",
             "privacy OR breach OR safety OR security",
             "lawsuit OR antitrust OR fraud OR regulators OR board"]

def fetch_gnews(company, window="6h"):
    queries = [f"{company} when:{window}"] + \
              [f"{company} ({t}) when:{window}" for t in ESG_TERMS]
    out = []
    for qs in queries:
        q = urllib.parse.quote(qs)
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
        for e in feed.entries:
            if e.get("published_parsed"):
                dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
            else:
                dt = datetime.now(timezone.utc)
            out.append(dict(title=e.title, url=e.link,
                            source=e.get("source", {}).get("title"),
                            published_at=dt, snippet=None, origin="gnews_rss"))
        time.sleep(2)
    return out

def fetch_newsdata(company):
    try:
        r = requests.get("https://newsdata.io/api/1/latest",
                         params={"apikey": ND_KEY, "q": company, "language": "en"}, timeout=30)
        data = r.json()
    except Exception as e:
        print("newsdata fail", company, e); return []
    if data.get("status") != "success":
        print("newsdata error", company, data.get("results"))
        return []
    out = []
    for a in data.get("results") or []:
        try:
            dt = datetime.strptime(a["pubDate"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
        out.append(dict(title=a.get("title"), url=a["link"], source=a.get("source_id"),
                        published_at=dt, snippet=a.get("description"), origin="newsdata"))
    return out

def resolve(url):
    if "news.google.com" in url:
        try:
            d = gnewsdecoder(url, interval=1)
            return d.get("decoded_url") if d.get("success") else None
        except Exception:
            return None
    return url

def fetch_body(url):
    try:
        real = resolve(url)
        if not real:
            return None
        r = requests.get(real, headers=UA, timeout=15)
        if r.status_code != 200:
            return None
        text = trafilatura.extract(r.text, include_comments=False)
        return text[:MAX_CHARS] if text and len(text) >= 300 else None
    except Exception as e:
        print("fetch_body error:", repr(e)[:100])
        return None

def fill_snippets():
    rows = (sb.table("articles").select("id,url")
            .is_("snippet", "null").eq("snippet_tried", False)
            .order("published_at", desc=True).limit(MAX_FETCH).execute().data)
    if not rows:
        return
    with ThreadPoolExecutor(6) as ex:
        bodies = list(ex.map(lambda r: fetch_body(r["url"]), rows))
    for r, b in zip(rows, bodies):
        sb.table("articles").update({"snippet": b, "snippet_tried": True}).eq("id", r["id"]).execute()
    print(f"snippets filled: {sum(1 for b in bodies if b)}/{len(rows)}")
    
def cleanup_empty():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    (sb.table("articles").delete()
       .is_("snippet", "null").eq("snippet_tried", True)
       .lt("created_at", cutoff).execute())

def run():
    for c in AI_GIANTS:
        merged = fetch_gnews(c)
        time.sleep(6)
        merged += fetch_newsdata(c)
        seen, rows = set(), []
        for a in sorted(merged, key=lambda x: x["published_at"], reverse=True):
            i = make_id(c, a["url"])
            if i in seen: continue
            seen.add(i)
            rows.append({**a, "id": i, "company": c,
                         "published_at": a["published_at"].isoformat()})
            if len(rows) == CAP: break
        if rows:
            res = sb.table("articles").upsert(rows, on_conflict="id", ignore_duplicates=True).execute()
            print(f"{c}: saved {len(res.data)} of {len(rows)}")
        else:
            print(f"{c}: nothing to save")
        print(f"{c}: {len(rows)} articles")
    fill_snippets() # this adds the snippet to the supabase, for the articles, it's missing!
    cleanup_empty() # this clears the remaining empty (NULL) snippets, after extracting the texts from all the sites! 

if __name__ == "__main__":
    run()
    for _ in range(10):
        left = (sb.table("articles").select("id", count="exact")
                .is_("snippet", "null").eq("snippet_tried", False)
                .limit(1).execute().count)
        if not left:
            break
        fill_snippets()
    