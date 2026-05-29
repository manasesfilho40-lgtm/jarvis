import json
import os
import re
from datetime import datetime
from pathlib import Path

try:
    from core.utils import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent

_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
_DEFAULT_VAULT = BASE_DIR / "memory" / "obsidian_vault"

def _get_vault_dir() -> Path:
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            custom_path = cfg.get("obsidian_vault_path", "")
            if custom_path:
                return Path(custom_path)
    except Exception:
        pass
    return _DEFAULT_VAULT

VAULT_DIR = _get_vault_dir()
CONVERSATIONS_FILE = VAULT_DIR / "Conversas.md"
FACTS_FILE = VAULT_DIR / "Fatos do Usuário.md"

def ensure_vault():
    """Garante que a pasta do Vault e os arquivos básicos existam."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    
    if not CONVERSATIONS_FILE.exists():
        with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
            f.write("# Histórico de Conversas com o JARVIS\n\n")
            f.write("Este arquivo registra as interações por texto e voz com o JARVIS.\n\n")

    if not FACTS_FILE.exists():
        update_facts_file()

def update_facts_file():
    """Exporta os fatos do long_term.json para Fatos do Usuário.md em formato amigável."""
    try:
        from memory.memory_manager import memory
        facts = memory.memory
        
        content = "# Fatos e Configurações do Usuário\n\n"
        content += "Estes fatos são lidos pelo JARVIS para personalizar suas respostas.\n\n"
        
        for category, items in facts.items():
            if isinstance(items, dict):
                if not items:
                    continue
                content += f"## {category.capitalize()}\n"
                for key, val in items.items():
                    if isinstance(val, dict) and "value" in val:
                        content += f"- **{key}**: {val['value']} *(Atualizado em: {val.get('updated', 'N/D')})*\n"
                    else:
                        content += f"- **{key}**: {val}\n"
                content += "\n"
            else:
                content += f"- **{category}**: {items}\n"
        
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        with open(FACTS_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"[Obsidian Memory Error] Falha ao atualizar fatos: {e}")

def add_to_history(user_msg: str, jarvis_msg: str):
    """Adiciona uma interação ao arquivo Conversas.md."""
    try:
        ensure_vault()
        
        user_msg = user_msg.strip() if user_msg else ""
        jarvis_msg = jarvis_msg.strip() if jarvis_msg else ""
        
        if not user_msg and not jarvis_msg:
            return
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(CONVERSATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(f"### {timestamp}\n")
            if user_msg:
                f.write(f"- **Usuário**: {user_msg}\n")
            if jarvis_msg:
                f.write(f"- **JARVIS**: {jarvis_msg}\n")
            f.write("\n")
            
        # Sempre atualiza o arquivo de fatos
        update_facts_file()
    except Exception as e:
        print(f"[Obsidian Memory Error] Falha ao gravar conversa: {e}")

def get_recent_history(limit: int = 15) -> str:
    """Lê os últimos N turnos da conversa para alimentar o prompt do JARVIS."""
    try:
        ensure_vault()
        if not CONVERSATIONS_FILE.exists():
            return ""
            
        with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Encontra blocos de conversa delimitados por ###
        turns = re.split(r"\n### ", content)
        if len(turns) <= 1:
            return ""
            
        # O primeiro elemento é o cabeçalho, os demais são os turnos
        recent_turns = turns[1:][-limit:]
        
        formatted = []
        for turn in recent_turns:
            lines = turn.strip().split("\n")
            timestamp = lines[0] if lines else ""
            msgs = []
            for line in lines[1:]:
                if line.startswith("- **Usuário**:") or line.startswith("- **JARVIS**:"):
                    msgs.append(line)
            if msgs:
                formatted.append(f"Em {timestamp}:\n" + "\n".join(msgs))
                
        return "\n\n".join(formatted)
    except Exception as e:
        print(f"[Obsidian Memory Error] Falha ao ler histórico: {e}")
        return ""
