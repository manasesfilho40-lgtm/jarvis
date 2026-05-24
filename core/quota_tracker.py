import json
from datetime import date
from pathlib import Path

TRACKER_PATH = Path(__file__).resolve().parent.parent / "config" / "quota_usage.json"

MODEL_LIMITS = {
    "gemini-2.5-flash": 20,
    "gemini-3.1-flash-live-preview": 120,
}

def _load():
    if TRACKER_PATH.exists():
        try:
            return json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save(data):
    TRACKER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def record_request(api_key: str, model: str):
    today = date.today().isoformat()
    data = _load()
    key_short = api_key[:8]
    entry = data.setdefault(today, {}).setdefault(key_short, {}).setdefault(model, 0)
    data[today][key_short][model] = entry + 1
    _save(data)

def get_usage(key_or_prefix: str, model: str) -> dict:
    today = date.today().isoformat()
    data = _load()
    limit = MODEL_LIMITS.get(model, 100)
    day_data = data.get(today, {})

    matcher = key_or_prefix[:8]
    count = 0
    for k, models in day_data.items():
        if matcher in k or k in matcher:
            count = models.get(model, 0)
            break

    return {
        "used": count,
        "limit": limit,
        "pct": round(min(100, (count / limit) * 100) if limit > 0 else 0),
        "model": model,
    }
