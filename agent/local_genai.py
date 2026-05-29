import urllib.request
import json
import re
from core.utils import BASE_DIR, get_api_key_safe as _get_api_key_safe

def configure(api_key=None):
    pass

class MockResponse:
    def __init__(self, text):
        self.text = text


def _get_api_key():
    return _get_api_key_safe()

def _load_settings() -> dict:
    try:
        settings_path = BASE_DIR / "config" / "model_settings.json"
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_settings(settings: dict) -> bool:
    try:
        settings_path = BASE_DIR / "config" / "model_settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        current = _load_settings()
        current.update(settings)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception as e:
        print(f"[LocalGenAI] Failed to save settings: {e}")
        return False

def set_routing_mode(mode: str) -> bool:
    if mode not in ("auto", "llama", "gemini"):
        return False
    return _save_settings({"routing_mode": mode})

def get_routing_mode() -> str:
    return _load_settings().get("routing_mode", "auto")

def set_ollama_model(model_name: str) -> bool:
    return _save_settings({"ollama_model": model_name})

def get_ollama_model() -> str:
    return _load_settings().get("ollama_model", "qwen2.5:3b")

def get_available_ollama_models() -> list:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"[LocalGenAI] Failed to list Ollama models: {e}")
        return []

def get_current_model_info() -> dict:
    mode = get_routing_mode()
    ollama_model = get_ollama_model()
    available = get_available_ollama_models()
    return {
        "mode": mode,
        "ollama_model": ollama_model,
        "available_models": available
    }

def is_complex_task(prompt, system_instruction=""):
    prompt_upper = str(prompt).upper()
    sys_upper = str(system_instruction).upper()
    
    # 1. If it requires writing python code or developer agent tasks
    if "EXPERT PYTHON DEVELOPER" in sys_upper or "WRITE CLEAN, COMPLETE PYTHON CODE" in sys_upper:
        return True
        
    # 2. If the prompt mentions complex tasks, analysis, coding, scraping, or web search
    complex_keywords = [
        "CODE", "CODIGO", "SCRIPT", "PROGRAMA", "PYTHON", "NEGOTIATION", "NEGOCIACAO",
        "APIFY", "SCRAPE", "BUSCA", "PESQUISA", "WEB SEARCH", "RESEARCH", "ANALISAR",
        "ANALYSIS", "COMPARE", "RELATORIO", "REPORT", "EXCEL", "SPREADSHEET", "PLANILHA"
    ]
    for kw in complex_keywords:
        if kw in prompt_upper:
            return True
            
    # 3. If the prompt length is long, suggesting detailed instructions or complexity
    if len(str(prompt)) > 150:
        return True
        
    return False

class GenerativeModel:
    def __init__(self, model_name="gemini-2.5-flash-lite", system_instruction=""):
        self.model_name = model_name
        self.system_instruction = system_instruction

    def generate_content(self, prompt, **kwargs):
        routing_mode = get_routing_mode()
            
        # Determine target brain
        use_gemini = False
        if routing_mode == "gemini":
            use_gemini = True
        elif routing_mode == "llama":
            use_gemini = False
        else: # "auto"
            use_gemini = is_complex_task(prompt, self.system_instruction)
            
        # Call the appropriate model
        if use_gemini:
            api_key = _get_api_key()
            if api_key:
                print(f"[LocalGenAI] 🧠 Routing to GEMINI (Cloud Brain) for prompt: '{str(prompt)[:60]}...'")
                try:
                    return self._generate_via_gemini(prompt, api_key)
                except Exception as e:
                    print(f"[LocalGenAI] [!]️ Gemini failed: {e}.")
                    try:
                        from core.api_rotator import rotate_api_key
                        rotate_api_key()
                    except Exception:
                        pass
                    print("[LocalGenAI] Falling back to local Llama 3...")
            else:
                print("[LocalGenAI] [!]️ Gemini API key not found. Routing to local Llama...")
                
        print(f"[LocalGenAI] [*] Routing to LOCAL BRAIN for prompt: '{str(prompt)[:60]}...'")
        return self._generate_via_llama(prompt)

    def _generate_via_gemini(self, prompt, api_key):
        if isinstance(prompt, (list, tuple)):
            prompt = "\n".join(str(p) for p in prompt)
            
        model = self.model_name
        if "lite" in model or "2.5-flash-lite" in model:
            model = "gemini-2.5-flash-lite"
        else:
            model = "gemini-2.5-flash"
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": str(prompt)}
                    ]
                }
            ]
        }
        
        if self.system_instruction:
            data["systemInstruction"] = {
                "parts": [
                    {"text": self.system_instruction}
                ]
            }
            
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=120) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                reply = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                return MockResponse(reply)
        except Exception as e:
            raise RuntimeError(f"Gemini generation request failed: {e}")

    def _generate_via_llama(self, prompt, model_name=None):
        if model_name is None:
            model_name = get_ollama_model()
        url = "http://127.0.0.1:11434/api/generate"
        headers = {"Content-Type": "application/json"}
        
        if isinstance(prompt, (list, tuple)):
            prompt = "\n".join(str(p) for p in prompt)
            
        system_instr = self.system_instruction
        
        if "You are the planning module" in system_instr:
            system_instr = """You are the planning module of MARK XXV. Break the goal into JSON steps.
TOOLS:
- open_app: {app_name} (e.g. "Brave", "Spotify", "Claude")
- web_search: {query}
- file_controller: {action: "write"|"read", path: "desktop"|path, name, content}
- send_message: {receiver, message_text, platform: "WhatsApp"}
- reminder: {date, time, message}
- youtube_video: {action: "play"|"summarize", query}
- computer_control: {action: "click"|"type"|"hotkey"|"press", text, x, y, keys, key}
- apify_leads: {actor_id: "compass/crawler-google-places", input_data: {"searchStringsArray": ["lojas de roupa em São Paulo"], "maxResults": 10}}
- whatsapp_web: {action: "send"|"autonomous"|"guard", target: "leads_results"|phone_number, message, product, timeout_minutes}
- negotiation_script: {action: "generate"|"load", product, price, max_discount, tone}
- manage_memory: {action: "store"|"retrieve"|"get_all", key, value}
- manage_crm: {action: "stats"|"list"|"get"|"mark_used"|"delete"|"clear", query, status, limit, phone}
- refresh_geopolitics: {}
- self_repair: {}

Return ONLY valid JSON in this exact structure:
{"goal": "...", "steps": [{"step": 1, "tool": "tool_name", "description": "...", "parameters": {}}]}"""

        elif "error recovery module" in system_instr:
            system_instr = """You are the error recovery module of MARK XXV.
Decide: "retry", "skip", "replan", or "abort".
Return ONLY valid JSON:
{"decision": "retry|skip|replan|abort", "reason": "why it failed", "fix_suggestion": "alternative tool", "max_retries": 1, "user_message": "15-word user alert"}"""

        elif "expert Python developer" in system_instr:
            system_instr = """You are an expert Python developer. Write clean, complete python code.
Return ONLY raw python code. No explanation, no markdown, no backticks."""

        data = {
            "model": model_name,
            "prompt": str(prompt),
            "stream": False
        }
        if system_instr:
            data["system"] = system_instr
            
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=120) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                reply = res_json.get("response", "").strip()
                
                if "steps" in reply or "decision" in reply:
                    start = reply.find("{")
                    end = reply.rfind("}")
                    if start != -1 and end != -1:
                        reply = reply[start:end+1]
                
                reply = re.sub(r"```(?:json|python)?", "", reply).strip().rstrip("`").strip()
                return MockResponse(reply)
        except Exception as e:
            if model_name != "llama3.2:3b":
                print(f"[LocalGenAI] [!]️ {model_name} failed: {e}. Retrying with llama3.2:3b...")
                return self._generate_via_llama(prompt, model_name="llama3.2:3b")
            print(f"[LocalGenAI Error] Failed to generate content via Ollama: {e}")
            raise RuntimeError(f"Ollama generation failed: {e}")
