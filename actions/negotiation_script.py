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
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

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
    2. objection_handling: How to respond to "it's too expensive", "I'll think about it", "not interested".
    3. counter_proposal: A way to offer a discount (max {max_discount}) while maintaining value and urgency.
    4. closing_message: Message to send when interest is high to finalize the deal.
    5. follow_up: Message for when the client stops responding.
    
    Return the response as a JSON object with these 5 keys.
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
    script_data = json.loads(raw)
    script_data["metadata"] = {
        "product": product,
        "price": price,
        "max_discount": max_discount,
        "tone": tone
    }
    
    filename = f"{product.lower().replace(' ', '_')}_script.json"
    file_path = SCRIPTS_DIR / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=4, ensure_ascii=False)
    
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
