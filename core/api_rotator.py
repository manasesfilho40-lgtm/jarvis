import json
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

def rotate_api_key() -> bool:
    """
    Rotates the active 'gemini_api_key' in config/api_keys.json
    using the list defined in 'gemini_api_keys'.
    Returns True if successfully rotated, False otherwise.
    """
    try:
        if not API_CONFIG_PATH.exists():
            return False

        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        keys = data.get("gemini_api_keys", [])
        
        # If gemini_api_keys list is not present, check if gemini_api_key itself is a list
        current_key = data.get("gemini_api_key")
        if isinstance(current_key, list):
            keys = current_key
            data["gemini_api_keys"] = keys
            
        if not keys or len(keys) <= 1:
            return False

        if current_key in keys:
            idx = keys.index(current_key)
            next_idx = (idx + 1) % len(keys)
        else:
            next_idx = 0

        new_key = keys[next_idx]
        data["gemini_api_key"] = new_key

        with open(API_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[API Key Rotator] Rotated active key to index {next_idx} ({new_key[:8]}...)")
        return True
    except Exception as e:
        print(f"[API Key Rotator] Error rotating API key: {e}")
        return False
