import json
import os
import re
import threading
from pathlib import Path
from datetime import datetime

_db_lock = threading.RLock()

def get_db_lock() -> threading.RLock:
    """Returns the shared lock for cross-module CRM synchronization."""
    return _db_lock

def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent

def _db_path() -> Path:
    db_path = _base_dir() / "config" / "leads_db.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

def normalize_phone(phone) -> str:
    if not phone:
        return ""
    return re.sub(r"[^\d]", "", str(phone))

def init_db() -> dict:
    with _db_lock:
        path = _db_path()
        if not path.exists():
            initial_data = {
                "new": [],
                "used": []
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2, ensure_ascii=False)
            return initial_data
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "new" not in data: data["new"] = []
                if "used" not in data: data["used"] = []
                _normalize_legacy_leads(data)
                return data
        except Exception:
            initial_data = {"new": [], "used": []}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2, ensure_ascii=False)
            return initial_data

def _normalize_legacy_leads(data: dict):
    """Converts old lead format {name, phone} to new format {title, phoneUnformatted}."""
    changed = False
    for section in ("new", "used"):
        for lead in data.get(section, []):
            if "name" in lead and "title" not in lead:
                lead["title"] = lead.pop("name")
                changed = True
            if "phone" in lead and "phoneUnformatted" not in lead:
                lead["phoneUnformatted"] = lead.pop("phone")
                changed = True
    if changed:
        _save_without_lock(data)

def _save_without_lock(data: dict):
    """Internal save that assumes caller already holds _db_lock."""
    path = _db_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_db(data: dict):
    with _db_lock:
        _save_without_lock(data)

def import_scraped_leads(scraped_leads: list) -> tuple:
    """
    Imports newly scraped leads. Avoids duplicates by checking existing leads' phones.
    """
    db = init_db()
    
    # Create lookup sets of existing phone numbers to avoid O(N^2) comparison
    existing_phones = set()
    for lead in db["new"]:
        phone = lead.get("phoneUnformatted")
        if phone:
            existing_phones.add(normalize_phone(phone))
            
    for lead in db["used"]:
        phone = lead.get("phoneUnformatted")
        if phone:
            existing_phones.add(normalize_phone(phone))

    added_count = 0
    duplicate_count = 0
    
    for lead in scraped_leads:
        raw_phone = (
            lead.get("phoneUnformatted") or 
            lead.get("phone") or 
            lead.get("phoneNumber") or 
            lead.get("phone_number") or 
            lead.get("telephone") or 
            lead.get("contactPhone")
        )
        if not raw_phone:
            continue
            
        clean_phone = normalize_phone(raw_phone)
        if not clean_phone:
            continue
            
        if clean_phone in existing_phones:
            duplicate_count += 1
            continue
            
        # Structure the new lead cleanly
        new_lead = {
            "title": lead.get("title") or lead.get("name") or "Cliente",
            "phoneUnformatted": raw_phone,
            "address": lead.get("address") or lead.get("fullAddress") or lead.get("street"),
            "website": lead.get("website") or lead.get("websiteUrl") or lead.get("url"),
            "categoryName": lead.get("categoryName") or lead.get("category"),
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        db["new"].append(new_lead)
        existing_phones.add(clean_phone)
        added_count += 1
        
    save_db(db)
    print(f"[LeadsManager] Imported leads: {added_count} new, {duplicate_count} skipped duplicates.")
    return added_count, duplicate_count

def get_new_leads() -> list:
    db = init_db()
    return db["new"]

def get_used_leads() -> list:
    db = init_db()
    return db["used"]

def mark_as_used(phone: str) -> bool:
    """
    Moves a lead from "new" to "used" by phone number.
    """
    db = init_db()
    clean_target = normalize_phone(phone)
    if not clean_target:
        return False
    
    found_idx = -1
    for idx, lead in enumerate(db["new"]):
        lead_phone = lead.get("phoneUnformatted")
        if lead_phone:
            clean_lead_phone = normalize_phone(lead_phone)
            if clean_lead_phone == clean_target:
                found_idx = idx
                break
                
    if found_idx != -1:
        lead = db["new"].pop(found_idx)
        lead["status"] = "contacted"
        lead["last_contacted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db["used"].append(lead)
        save_db(db)
        print(f"[LeadsManager] Marked {lead.get('title')} ({phone}) as USED.")
        return True

    return False

def get_crm_stats() -> dict:
    """Returns summary stats of the CRM database."""
    db = init_db()
    new_leads = db.get("new", [])
    used_leads = db.get("used", [])
    return {
        "new_count": len(new_leads),
        "used_count": len(used_leads),
        "total_count": len(new_leads) + len(used_leads),
        "last_imported": new_leads[-1].get("imported_at", "N/A") if new_leads else "N/A",
        "last_contacted": used_leads[-1].get("last_contacted_at", "N/A") if used_leads else "N/A"
    }

def search_leads(query: str = "", status: str = "all", limit: int = 10) -> list:
    """Searches leads by name, phone, or category. Returns formatted results."""
    db = init_db()
    results = []

    pools = []
    if status in ("new", "all"):
        pools.extend(db.get("new", []))
    if status in ("used", "all"):
        pools.extend(db.get("used", []))

    query_lower = query.lower().strip() if query else ""

    for lead in pools:
        if query_lower:
            title = str(lead.get("title", "")).lower()
            phone = str(lead.get("phoneUnformatted", ""))
            category = str(lead.get("categoryName", "")).lower()
            address = str(lead.get("address", "")).lower()
            if not (query_lower in title or query_lower in phone or query_lower in category or query_lower in address):
                continue

        results.append({
            "title": lead.get("title", "Cliente"),
            "phone": lead.get("phoneUnformatted", ""),
            "address": lead.get("address", ""),
            "website": lead.get("website", ""),
            "category": lead.get("categoryName", ""),
            "status": lead.get("status", "new") if "status" in lead else "new",
            "imported_at": lead.get("imported_at", "")
        })

        if len(results) >= limit:
            break

    return results

def delete_lead(phone: str) -> bool:
    """Deletes a specific lead from both new and used lists by phone number."""
    db = init_db()
    clean_target = normalize_phone(phone)
    if not clean_target:
        return False

    for section in ("new", "used"):
        for idx, lead in enumerate(db.get(section, [])):
            lead_phone = normalize_phone(lead.get("phoneUnformatted", ""))
            if lead_phone == clean_target:
                removed = db[section].pop(idx)
                save_db(db)
                print(f"[LeadsManager] Deleted lead {removed.get('title')} ({phone}) from {section}.")
                return True

    return False

def clear_leads(status: str = "all") -> int:
    """Clears leads by status. Returns count of removed leads."""
    db = init_db()
    count = 0

    if status in ("new", "all"):
        count += len(db.get("new", []))
        db["new"] = []
    if status in ("used", "all"):
        count += len(db.get("used", []))
        db["used"] = []

    save_db(db)
    print(f"[LeadsManager] Cleared {count} leads (status: {status}).")
    return count

def system_dashboard() -> dict:
    """Returns a comprehensive system status dashboard."""
    status = {"crm": {}, "apify": {}, "scripts": {}, "system": {}}

    # CRM stats
    try:
        status["crm"] = get_crm_stats()
    except Exception as e:
        status["crm"]["error"] = str(e)

    # Apify scrape status
    try:
        from actions.apify_leads import get_scrape_status
        scrape = get_scrape_status()
        cur = scrape.get("current", {})
        status["apify"] = {
            "status": cur.get("status", "idle"),
            "details": cur.get("details", ""),
            "updated_at": cur.get("updated_at", ""),
            "history_count": len(scrape.get("history", []))
        }
    except Exception as e:
        status["apify"]["error"] = str(e)

    # Scripts
    try:
        scripts_dir = _base_dir() / "memory" / "scripts"
        script_files = list(scripts_dir.glob("*_script.json")) if scripts_dir.exists() else []
        status["scripts"] = {
            "total": len(script_files),
            "names": [f.stem.replace("_script", "") for f in script_files]
        }
    except Exception as e:
        status["scripts"]["error"] = str(e)

    # System
    status["system"] = {
        "python_version": os.sys.version.split()[0],
        "module_dir": str(_base_dir())
    }

    return status


def format_dashboard(status: dict) -> str:
    """Formats dashboard dict as a human-readable string."""
    lines = ["=== JARVIS SYSTEM DASHBOARD ===\n"]

    crm = status.get("crm", {})
    lines.append("--- CRM ---")
    lines.append(f"  Novos: {crm.get('new_count', '?')}")
    lines.append(f"  Contactados: {crm.get('used_count', '?')}")
    lines.append(f"  Total: {crm.get('total_count', '?')}")
    lines.append(f"  Última importação: {crm.get('last_imported', 'N/A')}")
    lines.append(f"  Último contato: {crm.get('last_contacted', 'N/A')}")

    apify = status.get("apify", {})
    lines.append("\n--- Apify Scraping ---")
    lines.append(f"  Status: {apify.get('status', '?')}")
    lines.append(f"  Detalhes: {apify.get('details', 'N/A')}")
    lines.append(f"  Última atualização: {apify.get('updated_at', 'N/A')}")
    lines.append(f"  Histórico: {apify.get('history_count', 0)} execuções")

    scripts = status.get("scripts", {})
    lines.append(f"\n--- Scripts de Negociação ---")
    lines.append(f"  Carregados: {scripts.get('total', 0)}")
    for name in scripts.get("names", []):
        lines.append(f"    - {name}")

    sysinfo = status.get("system", {})
    lines.append(f"\n--- Sistema ---")
    lines.append(f"  Python: {sysinfo.get('python_version', '?')}")
    lines.append(f"  Diretório: {sysinfo.get('module_dir', '?')}")

    lines.append("\n==============================")
    return "\n".join(lines)

def manage_crm(parameters: dict) -> str:
    """Main entry point for CRM operations callable by Jarvis."""
    action = parameters.get("action", "stats")

    if action == "dashboard":
        status = system_dashboard()
        return format_dashboard(status)

    if action == "stats":
        stats = get_crm_stats()
        return (
            f"CRM Stats:\n"
            f"- Leads novos: {stats['new_count']}\n"
            f"- Leads contactados: {stats['used_count']}\n"
            f"- Total: {stats['total_count']}\n"
            f"- Última importação: {stats['last_imported']}\n"
            f"- Último contato: {stats['last_contacted']}"
        )

    elif action == "list":
        query = parameters.get("query", "")
        status = parameters.get("status", "new")
        limit = parameters.get("limit", 10)
        leads = search_leads(query=query, status=status, limit=limit)
        if not leads:
            return f"Nenhum lead encontrado{' com filtro' if query else ''}."
        output = [f"Encontrados {len(leads)} leads:"]
        for i, lead in enumerate(leads, 1):
            output.append(
                f"{i}. {lead['title']} | {lead['phone']} | {lead['category']} | {lead['address']}"
            )
        return "\n".join(output)

    elif action == "get":
        query = parameters.get("query", "")
        if not query:
            return "ERROR: query parameter is required for get action (search by name or phone)."
        leads = search_leads(query=query, status="all", limit=1)
        if not leads:
            return f"Nenhum lead encontrado para '{query}'."
        lead = leads[0]
        return (
            f"Lead: {lead['title']}\n"
            f"Telefone: {lead['phone']}\n"
            f"Endereço: {lead['address']}\n"
            f"Site: {lead['website'] or 'N/A'}\n"
            f"Categoria: {lead['category']}\n"
            f"Status: {lead['status']}\n"
            f"Importado em: {lead['imported_at']}"
        )

    elif action == "mark_used":
        phone = parameters.get("phone", "")
        if not phone:
            return "ERROR: phone parameter is required for mark_used action."
        success = mark_as_used(phone)
        return f"Lead {phone} marcado como contactado." if success else f"Lead {phone} não encontrado na fila de novos."

    elif action == "delete":
        phone = parameters.get("phone", "")
        if not phone:
            return "ERROR: phone parameter is required for delete action."
        success = delete_lead(phone)
        return f"Lead {phone} removido do CRM." if success else f"Lead {phone} não encontrado."

    elif action == "clear":
        status = parameters.get("status", "all")
        count = clear_leads(status=status)
        return f"{count} leads removidos (status: {status})."

    return f"ERROR: Unknown action '{action}'. Use: stats, list, get, mark_used, delete, clear."
