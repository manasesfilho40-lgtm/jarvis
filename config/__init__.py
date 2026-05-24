from core.utils import get_api_key, get_api_key_safe

def get_config() -> dict:
    return {"gemini_api_key": get_api_key()}

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    try:
        config = get_config()
        return config.get("os_system", "windows").lower()
    except Exception:
        return "windows"

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
