import json
import os
from pathlib import Path
from google import genai
from google.genai import types

def get_base_dir():
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
SCRIPTS_DIR = BASE_DIR / "memory" / "scripts"
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            key = data.get("gemini_api_key", "")
            if not key:
                keys = data.get("gemini_api_keys", [])
                key = keys[0] if keys else ""
            return key
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        return ""

def generate_negotiation_script(product, price, max_discount, tone):
    """
    Generates a full negotiation script using Gemini.
    """
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    client = genai.Client(api_key=_get_api_key())
    
    prompt = f"""
    You are an expert sales strategist. Create a complete sales and negotiation script for a freelancer designer.
    
    Context:
    - Product/Service: {product}
    - Price: {price}
    - Max Discount allowed: {max_discount}
    - Tone: {tone}
    
    User Business Info:
    - Freelance designer creating ad layouts for clothing stores.
    - Sales process: Check if sells online -> show portfolio -> ask engagement question -> present pack price -> create urgency -> negotiate if needed.
    
    Generate the following 5 parts:
    1. opening_message: Initial contact, asking if they sell online and introducing the value.
    2. objection_handling: An object with exactly these 8 keys (each is a short reply):
       - "nao_temos_interesse": client says not interested
       - "ja_temos_agencia": client already has an agency
       - "preco_alto": client says it's too expensive
       - "sem_verba_agora": client says no budget right now
       - "preciso_consultar": client needs to consult someone else
       - "manda_email": client asks to send via email
       - "nao_confio": client doesn't know/trust you
       - "ja_temos_fornecedor": client already has a supplier
    3. counter_proposal: A way to offer a discount (max {max_discount}) while maintaining value and urgency.
    4. closing_message: Message to send when interest is high to finalize the deal.
    5. follow_up: Message for when the client stops responding.
    6. urgency_triggers: An object with keys:
       - "scarcity": short message about limited availability
       - "social_proof": short message about results from other clients
    
    Return the response as a JSON object with these 6 keys. objection_handling must be a JSON object with the 8 keys above.
    """
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    
    try:
        script_data = json.loads(raw)
    except json.JSONDecodeError:
        return "Error: Gemini returned invalid JSON for the negotiation script."
    
    script_data["metadata"] = {
        "product": product,
        "price": price,
        "max_discount": max_discount,
        "tone": tone
    }
    
    filename = f"{product.lower().replace(' ', '_')}_script.json"
    file_path = SCRIPTS_DIR / filename
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(script_data, f, indent=4, ensure_ascii=False)
    except OSError as e:
        return f"Error: Could not save script file: {e}"
    
    return f"Script generated and saved to {file_path}"

def load_script(product_name):
    filename = f"{product_name.lower().replace(' ', '_')}_script.json"
    file_path = SCRIPTS_DIR / filename
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def negotiation_script_action(parameters, player=None):
    action = parameters.get("action", "generate")
    product = parameters.get("product")
    price = parameters.get("price")
    max_discount = parameters.get("max_discount", "0%")
    tone = parameters.get("tone", "professional")
    
    if action == "generate":
        if not product or not price:
            return "Error: product and price are required for generation."
        return generate_negotiation_script(product, price, max_discount, tone)
    
    elif action == "load":
        script = load_script(product)
        if script:
            return f"Script loaded: {json.dumps(script, indent=2, ensure_ascii=False)}"
        return f"No script found for {product}."
    
    return "Unknown action."
