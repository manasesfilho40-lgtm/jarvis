import json
import traceback
from datetime import datetime
from core.utils import API_CONFIG_PATH, get_api_key_safe as _get_api_key

def _get_api_keys_list() -> list[str]:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        keys = data.get("gemini_api_keys", [])
        if not keys:
            key = data.get("gemini_api_key", "")
            if isinstance(key, list):
                keys = key
            elif key:
                keys = [key]
        return keys
    except Exception:
        return []

FALLBACK_NEWS = [
    {
        "category": "war",
        "title": "Ucrânia: novos ataques reportados na região de Kharkiv",
        "body": "Forças russas intensificam bombardeios no leste. OTAN monitora fronteira.",
        "region": "🇺🇦 Europa Oriental",
        "time": "há 15 min",
        "lat": 50.4, "lon": 30.5
    },
    {
        "category": "alert",
        "title": "Gaza: negociações de cessar-fogo entram em nova rodada",
        "body": "Mediadores internacionais buscam acordo. Tensão permanece alta na região.",
        "region": "🇵🇸 Oriente Médio",
        "time": "há 30 min",
        "lat": 31.7, "lon": 35.2
    },
    {
        "category": "market",
        "title": "FED sinaliza manutenção de juros altos por mais tempo",
        "body": "Bancos centrais ajustam projeções. Dólar volatiliza frente a emergentes.",
        "region": "🇺🇸 EUA",
        "time": "há 1h",
        "lat": 40.7, "lon": -74.0
    },
    {
        "category": "geo",
        "title": "Tensão no Estreito de Taiwan com exercícios navais",
        "body": "Movimentação militar ativa protocolos de defesa no Japão e Coreia do Sul.",
        "region": "🇨🇳 Indo-Pacífico",
        "time": "há 2h",
        "lat": 23.5, "lon": 121.0
    },
    {
        "category": "tech",
        "title": "Nova IA generativa chinesa desafia liderança do Vale do Silício",
        "body": "Empresa de Shenzhen lança modelo com desempenho superior em benchmarks.",
        "region": "🇨🇳 China",
        "time": "há 3h",
        "lat": 22.5, "lon": 114.1
    },
    {
        "category": "energy",
        "title": "OPEP+ anuncia corte adicional na produção de petróleo",
        "body": "Decisão visa estabilizar preços. Impacto esperado nos mercados globais.",
        "region": "🇸🇦 Arábia Saudita",
        "time": "há 4h",
        "lat": 24.5, "lon": 54.6
    },
    {
        "category": "health",
        "title": "OMS alerta para surto de dengue na América Latina",
        "body": "Casos aumentam 40% na região. Brasil lidera campanhas de vacinação.",
        "region": "🇧🇷 Brasil",
        "time": "há 5h",
        "lat": -23.5, "lon": -46.6
    },
    {
        "category": "climate",
        "title": "Cúpula do Clima: novos limites de emissões em Bruxelas",
        "body": "Líderes europeus propõem metas mais rígidas para o setor industrial.",
        "region": "🇪🇺 União Europeia",
        "time": "há 6h",
        "lat": 50.8, "lon": 4.3
    },
    {
        "category": "market",
        "title": "Bitcoin supera resistência e testa nova máxima do ano",
        "body": "Institucionais aumentam exposição. ETFs registram entradas recordes.",
        "region": "🌐 Global",
        "time": "há 2h",
        "lat": 37.8, "lon": -122.4
    },
    {
        "category": "alert",
        "title": "Terremoto de magnitude 6.2 atinge costa do Japão",
        "body": "Alerta de tsunami emitido e depois cancelado. Sem danos graves reportados.",
        "region": "🇯🇵 Japão",
        "time": "há 1h",
        "lat": 35.7, "lon": 139.7
    }
]

FALLBACK_MARKETS = [
    {"name": "S&P 500", "val": "5.847", "delta": "+0.82", "up": True},
    {"name": "BTC/USD", "val": "67.4k", "delta": "+2.1", "up": True},
    {"name": "Petróleo", "val": "$88.3", "delta": "-1.3", "up": False},
    {"name": "IBOV", "val": "128.4k", "delta": "-0.4", "up": False},
    {"name": "EUR/USD", "val": "1.087", "delta": "+0.15", "up": True},
    {"name": "Ouro", "val": "$2.341", "delta": "+0.6", "up": True},
]

def _try_fetch(api_key: str) -> dict | None:
    from google import genai
    from core.quota_tracker import record_request

    client = genai.Client(api_key=api_key)

    prompt = (
        "Using Google Search, find the top 10 high-impact, REAL geopolitical events, "
        "military conflicts, major financial market shifts, or crises happening globally RIGHT NOW (last 24 hours). "
        "Return a clean JSON object with these keys:\n\n"
        "'news': A JSON array of exactly 10 objects. MUST include diversity across regions and categories:\n"
        "  - At least 1 from Americas (North or South)\n"
        "  - At least 1 from Europe\n"
        "  - At least 1 from Middle East or Africa\n"
        "  - At least 1 from Asia-Pacific\n"
        "  - At least 1 from Brazil or Latin America\n"
        "  - Mix of categories: 'war', 'market', 'geo', 'alert', 'tech', 'energy', 'health', 'climate'\n"
        "  Each object with:\n"
        "  - 'category': one of 'war', 'market', 'geo', 'alert', 'tech', 'energy', 'health', 'climate'\n"
        "  - 'title': Headline in Brazilian Portuguese (max 80 chars)\n"
        "  - 'body': Brief explanation in Brazilian Portuguese (1-2 sentences, max 160 chars)\n"
        "  - 'region': Region with flag emoji (e.g. '🇺🇦 Europa Oriental', '🇧🇷 Brasil', '🇺🇸 EUA', '🇯🇵 Japão', '🇿🇦 África do Sul')\n"
        "  - 'time': Relative time ('há 10 min', 'há 1h', 'há 3h')\n"
        "  - 'lat': Latitude of the event location (approximate)\n"
        "  - 'lon': Longitude of the event location (approximate)\n\n"
        "'markets': A JSON array of 6 market tickers. Each with:\n"
        "  - 'name': Ticker name (e.g. 'S&P 500', 'BTC/USD', 'IBOV', 'EUR/USD', 'Ouro', 'Petróleo')\n"
        "  - 'val': Current value as string (e.g. '5.847', '67.4k', '$88.3')\n"
        "  - 'delta': Percentage change as string without sign (e.g. '0.82', '1.3')\n"
        "  - 'up': boolean (true if positive, false if negative)\n\n"
        "'threat_level': One of 'low', 'moderate', 'elevated', 'high', 'critical'\n\n"
        "Respond ONLY with the JSON object. No markdown, no code blocks. "
        "Use REAL current data from Google Search. Prioritize news from the last 12 hours."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "tools": [{"google_search": {}}],
        },
    )

    raw = ""
    if response.candidates and response.candidates[0].content.parts:
        raw = response.candidates[0].content.parts[0].text or ""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    data = json.loads(raw)
    record_request(api_key, "gemini-2.5-flash")

    if "news" not in data:
        data["news"] = FALLBACK_NEWS
    if "markets" not in data:
        data["markets"] = FALLBACK_MARKETS
    if "threat_level" not in data:
        data["threat_level"] = "moderate"

    data["updated_at"] = datetime.now().strftime("%H:%M")

    print(f"[Geopolitics Monitor] Fetched {len(data['news'])} live updates. Threat: {data['threat_level']}")
    return data


def fetch_geopolitics_news() -> str:
    try:
        from core.api_rotator import rotate_api_key
    except ImportError:
        rotate_api_key = None

    api_key = _get_api_key()
    if not api_key:
        print("[Geopolitics Monitor] No API key found. Using fallback.")
        return json.dumps({
            "news": FALLBACK_NEWS,
            "markets": FALLBACK_MARKETS,
            "threat_level": "moderate",
            "updated_at": datetime.now().strftime("%H:%M")
        }, ensure_ascii=False)

    last_error = None
    max_attempts = max(len(_get_api_keys_list()), 1)

    for attempt in range(max_attempts):
        try:
            data = _try_fetch(api_key)
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            last_error = e
            err_str = str(e).upper()
            if ("RESOURCE_EXHAUSTED" in err_str or "429" in err_str or "QUOTA" in err_str) and rotate_api_key:
                print(f"[Geopolitics Monitor] Quota exceeded for key. Rotating... (attempt {attempt + 1}/{max_attempts})")
                if rotate_api_key():
                    api_key = _get_api_key()
                    import time
                    time.sleep(2)
                    continue
            else:
                break

    print(f"[Geopolitics Monitor] All keys exhausted or fetch failed: {last_error}. Using fallback.")
    traceback.print_exc()
    return json.dumps({
        "news": FALLBACK_NEWS,
        "markets": FALLBACK_MARKETS,
        "threat_level": "moderate",
        "updated_at": datetime.now().strftime("%H:%M")
    }, ensure_ascii=False)

if __name__ == "__main__":
    print(fetch_geopolitics_news())
