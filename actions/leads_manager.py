import json
from pathlib import Path
from datetime import datetime

def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent

def _db_path() -> Path:
    db_path = _base_dir() / "config" / "leads_db.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

def init_db() -> dict:
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
            # Guarantee structure
            if "new" not in data: data["new"] = []
            if "used" not in data: data["used"] = []
            return data
    except Exception:
        # Recreate if corrupt
        initial_data = {"new": [], "used": []}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, indent=2, ensure_ascii=False)
        return initial_data

def save_db(data: dict):
    path = _db_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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
            existing_phones.add(str(phone).strip().replace("+", "").replace(" ", "").replace("-", ""))
            
    for lead in db["used"]:
        phone = lead.get("phoneUnformatted")
        if phone:
            existing_phones.add(str(phone).strip().replace("+", "").replace(" ", "").replace("-", ""))

    added_count = 0
    duplicate_count = 0
    
    for lead in scraped_leads:
        raw_phone = lead.get("phoneUnformatted")
        if not raw_phone:
            continue
            
        clean_phone = str(raw_phone).strip().replace("+", "").replace(" ", "").replace("-", "")
        if not clean_phone:
            continue
            
        if clean_phone in existing_phones:
            duplicate_count += 1
            continue
            
        # Structure the new lead cleanly
        new_lead = {
            "title": lead.get("title", "Cliente"),
            "phoneUnformatted": raw_phone,
            "address": lead.get("address"),
            "website": lead.get("website"),
            "categoryName": lead.get("categoryName"),
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
    clean_target = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    
    found_idx = -1
    for idx, lead in enumerate(db["new"]):
        lead_phone = lead.get("phoneUnformatted")
        if lead_phone:
            clean_lead_phone = str(lead_phone).strip().replace("+", "").replace(" ", "").replace("-", "")
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
