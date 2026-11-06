import os, pickle
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import joblib
import numpy as np

import torch
from dotenv import load_dotenv
from supabase import create_client
from train_model import ESGModel   # must be importable so pickle can rebuild the BERT class

load_dotenv()
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# ---------- config ----------
BASE = Path(os.getenv("MODELS_DIR", Path(__file__).resolve().parent / "models and encoders"))
ESG_DIR, BERT_DIR = BASE / "ESG news ml classifier", BASE / "ModernBERT"
CONF_MIN = 0.5       # below this, an E/S/G prediction is treated as not ESG
MAX_CHARS = 1500      # same text format as the labeled dataset
MAX_LENGTH = 512      # must match BERT training
ESG_CLASSES = {"E", "S", "G"}

for d in (ESG_DIR, BERT_DIR):
    if not d.is_dir():
        raise FileNotFoundError(f"Model folder not found: {d} (check MODELS_DIR / the HF download step)")

def load(path):
    with open(path, "rb") as f:
        return pickle.load(f)

# ---------- load models ----------
esg_vec   = joblib.load(ESG_DIR / "vectorizer.pkl")
esg_model = joblib.load(ESG_DIR / "log_reg_esg_model.pkl")      # use your actual filename
esg_le    = joblib.load(ESG_DIR / "le.pkl")
bert_tok  = load(BERT_DIR / "tokenizer.pkl")
bert_model = load(BERT_DIR / "modernBERT_model.pkl")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
bert_model = bert_model.to(DEVICE).eval()
print("Device:", DEVICE, "| ESG classes:", list(esg_le.classes_))

import time

def with_retry(fn, tries=5):
    global sb
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            wait = 3 * (i + 1)
            print(f"network error ({type(e).__name__}), retry {i+1}/{tries} in {wait}s")
            time.sleep(wait)
            sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))  # fresh connection
    raise RuntimeError("Supabase unreachable after retries")

# ---------- model 1: ESG gate (whole batch at once) ----------
def classify_esg(texts):
    probs = esg_model.predict_proba(esg_vec.transform(texts))
    idx = probs.argmax(axis=1)
    raw = esg_model.classes_[idx]
    if np.issubdtype(raw.dtype, np.integer):
        raw = esg_le.inverse_transform(raw)
    return [str(x) for x in raw], [round(float(p), 3) for p in probs.max(axis=1)]

# ---------- model 2: ModernBERT ----------
@torch.inference_mode()
def predict_aspect(text):
    enc = bert_tok(text, truncation=True, padding="max_length",
                   max_length=MAX_LENGTH, return_tensors="pt")
    a, r, s = bert_model(enc["input_ids"].to(DEVICE), enc["attention_mask"].to(DEVICE))
    aspects = ["environmental", "social", "governance"]
    relevance_values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    sentiments = ["negative", "neutral", "positive"]
    return (aspects[a.argmax(dim=1).item()],
            relevance_values[r.argmax(dim=1).item()],
            sentiments[s.argmax(dim=1).item()])

def impact_score(aspect, relevance, sentiment):
    signs = {"negative": -1, "neutral": 0, "positive": 1}
    return round(float(relevance) * signs[sentiment.lower()] * 100, 2)

# ---------- main ----------
def run(batch=200):
    stats = Counter()
    while True:
        rows = with_retry(lambda: sb.table("articles").select("id,title,snippet")
                          .is_("processed_at", "null").not_.is_("snippet", "null")
                          .limit(batch).execute()).data
        if not rows:
            break

        texts = [f"{r['title'] or ''}. {r['snippet'][:MAX_CHARS]}".strip() for r in rows]
        try:
            labels, confs = classify_esg(texts)
        except Exception as e:
            print("ESG classifier failed, stopping:", repr(e)[:150])
            break

        now = datetime.now(timezone.utc).isoformat()
        for r, text, label, conf in zip(rows, texts, labels, confs):
            upd = {"processed_at": now, "esg_label": label, "esg_conf": conf}
            if label in ESG_CLASSES and conf >= CONF_MIN:
                try:
                    a, rel, sen = predict_aspect(text)
                    upd.update(aspect=a, relevance=float(rel), sentiment=sen,
                               impact_score=impact_score(a, rel, sen))
                    stats["scored"] += 1
                except Exception as e:
                    print("BERT failed:", r["id"], repr(e)[:100])
                    upd["esg_label"] = "ERROR"
                    stats["error"] += 1
            else:
                stats["not_esg"] += 1
            with_retry(lambda: sb.table("articles").update(upd).eq("id", r["id"]).execute())
        print(f"batch of {len(rows)} done | totals: {dict(stats)}")
        
if __name__ == "__main__":
    run()