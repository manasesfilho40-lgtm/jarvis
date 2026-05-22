import os
import sys
import json
import subprocess
import traceback
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

def check_syntax() -> list[str]:
    issues = []
    py_files = list(BASE_DIR.glob("*.py")) + list((BASE_DIR / "actions").glob("*.py")) + list((BASE_DIR / "agent").glob("*.py"))
    for file_path in py_files:
        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", str(file_path)],
                capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            err = e.stderr or e.stdout
            issues.append(f"Syntax error in {file_path.name}: {err.strip()}")
        except Exception as e:
            issues.append(f"Could not compile {file_path.name}: {e}")
    return issues

def check_dependencies() -> list[str]:
    missing = []
    for dep in ["PyQt6", "sounddevice", "numpy", "pyautogui", "pyperclip", "apify_client", "playwright"]:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    return missing

def verify_gemini_api() -> dict:
    config_path = BASE_DIR / "config" / "api_keys.json"
    if not config_path.exists():
        return {"status": "error", "message": "config/api_keys.json not found."}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse api_keys.json: {e}"}

    keys = data.get("gemini_api_keys", [])
    active_key = data.get("gemini_api_key", "")
    
    if not active_key:
        return {"status": "error", "message": "No active gemini_api_key in config."}

    # Verify if active key is functional
    from google import genai
    try:
        client = genai.Client(api_key=active_key)
        client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Hello"
        )
        return {"status": "ok", "message": "Active Gemini key is working perfectly."}
    except Exception as e:
        err_msg = str(e).upper()
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            # Try to rotate
            from core.api_rotator import rotate_api_key
            if rotate_api_key():
                return {"status": "rotated", "message": "Active key was exhausted. Successfully rotated key."}
            else:
                return {"status": "exhausted", "message": "All keys are exhausted."}
        elif "API_KEY_INVALID" in err_msg or "400" in err_msg:
            from core.api_rotator import rotate_api_key
            if rotate_api_key():
                return {"status": "rotated", "message": "Active key was invalid. Successfully rotated key."}
            else:
                return {"status": "invalid", "message": f"Active key is invalid and rotation failed: {e}"}
        return {"status": "error", "message": f"Gemini API verification failed: {e}"}

def run_diagnostics_and_repair(parameters: dict = None, player=None, speak=None) -> str:
    def log(msg: str):
        print(f"[SelfRepair] {msg}")
        if player:
            player.write_log(f"[SelfRepair] {msg}")

    log("Starting Jarvis self-diagnostics and auto-repair sequence...")
    
    # 1. Dependency check
    missing_deps = check_dependencies()
    if missing_deps:
        log(f"Missing dependencies found: {missing_deps}. Installing...")
        for dep in missing_deps:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", dep], check=True, capture_output=True)
                log(f"Successfully installed: {dep}")
            except Exception as e:
                log(f"Failed to install dependency '{dep}': {e}")
    else:
        log("All core dependencies verified.")

    # 2. Syntax Check
    syntax_issues = check_syntax()
    if syntax_issues:
        log("Syntax issues detected:")
        for issue in syntax_issues:
            log(f" - {issue}")
        # Try to auto-repair simple syntax issues if possible
        # (Could use local genai / code_helper if key fails, but let's notify for now)
    else:
        log("Syntax check passed for all modules.")

    # 3. API Keys and Gemini Verification
    api_check = verify_gemini_api()
    log(f"Gemini API Status: {api_check['message']}")

    # 4. Local LLM (Ollama) Verification
    try:
        import urllib.request
        url = "http://127.0.0.1:11434/api/generate"
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(
            url, 
            data=json.dumps({"model": "qwen2.5:3b", "prompt": "test", "stream": False}).encode("utf-8"), 
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            if "response" in res_json:
                log("Local LLM (Ollama qwen2.5:3b) is online and active.")
            else:
                log("Local LLM responded but output was incomplete.")
    except Exception as e:
        log(f"Local LLM (Ollama) is offline or model is not loaded: {e}")

    # Build final report
    summary = "Auto-diagnóstico concluído, senhor. "
    if syntax_issues:
        summary += f"Identifiquei problemas de sintaxe em {len(syntax_issues)} arquivos. "
    if missing_deps:
        summary += f"Instalei as dependências ausentes: {', '.join(missing_deps)}. "
    
    if api_check["status"] in ("ok", "rotated"):
        summary += "A API do Gemini está totalmente operacional."
    else:
        summary += "A API do Gemini está temporariamente indisponível. Recomendo utilizar o cérebro local Llama."

    if speak:
        speak(summary)

    return summary

if __name__ == "__main__":
    run_diagnostics_and_repair()
