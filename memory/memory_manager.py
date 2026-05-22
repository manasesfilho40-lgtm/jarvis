import json
import os
from pathlib import Path

class MemoryManager:
    def __init__(self, memory_file=None):
        if memory_file is None:
            base = Path(__file__).resolve().parent
            memory_file = base / "long_term.json"
        self.memory_file = Path(memory_file)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory = self._load_memory()

    def _load_memory(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_memory(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)

    def store(self, key, value):
        """Stores a fact about the user."""
        self.memory[key] = value
        self._save_memory()
        try:
            from memory.obsidian_manager import update_facts_file
            update_facts_file()
        except Exception:
            pass
        return f"Fact stored: {key} = {value}"

    def retrieve(self, key):
        """Retrieves a fact."""
        return self.memory.get(key, "Information not found.")

    def get_all(self):
        """Returns all stored facts as a string for the AI prompt."""
        if not self.memory:
            return "No personal information stored yet."
        
        lines = []
        def parse_item(k, v, indent=0):
            prefix = "  " * indent
            if isinstance(v, dict):
                if "value" in v:
                    lines.append(f"{prefix}- {k}: {v['value']}")
                else:
                    # Don't show empty dicts
                    if not v:
                        return
                    lines.append(f"{prefix}- {k}:")
                    for sub_k, sub_v in v.items():
                        parse_item(sub_k, sub_v, indent + 1)
            else:
                lines.append(f"{prefix}- {k}: {v}")
                
        for k, v in self.memory.items():
            parse_item(k, v)
        return "\n".join(lines)

# Global instance
memory = MemoryManager()

def manage_memory(parameters):
    action = parameters.get("action")
    key = parameters.get("key")
    value = parameters.get("value")

    if action == "store":
        return memory.store(key, value)
    elif action == "retrieve":
        return memory.retrieve(key)
    elif action == "get_all":
        return memory.get_all()
    return "Invalid action for memory management."