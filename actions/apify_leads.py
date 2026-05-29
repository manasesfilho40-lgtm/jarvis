import json
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from apify_client import ApifyClient

_VALID_ACTORS = {
    "compass/crawler-google-places",
    "apify/instagram-scraper",
    "apify/facebook-pages-scraper",
}

def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent

def _status_path() -> Path:
    return _base_dir() / "config" / "apify_status.json"

def _get_token() -> str:
    try:
        cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return cfg.get("apify_token", "")
    except Exception:
        return ""

def _set_status(status: str, details: str = ""):
    """Persist scrape status so other modules can query it."""
    entry = {
        "status": status,
        "details": details,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        path = _status_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {"history": []}
        else:
            data = {"history": []}
        if "history" not in data:
            data["history"] = []
        data["current"] = entry
        data["history"].append(entry)
        data["history"] = data["history"][-20:]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[Apify Status Error] {e}")

def _map_input(actor_id: str, input_data) -> dict:
    if isinstance(input_data, str):
        try:
            input_data = json.loads(input_data)
        except Exception:
            input_data = {"search": input_data}

    if not isinstance(input_data, dict):
        input_data = {}

    if "crawler-google-places" in actor_id or "google-maps-scraper" in actor_id:
        q = (
            input_data.get("search") or
            input_data.get("query") or
            input_data.get("location") or
            input_data.get("searchStringsArray") or
            input_data.get("queries")
        )
        if q:
            if isinstance(q, str):
                input_data["searchStringsArray"] = [q]
            elif isinstance(q, list):
                input_data["searchStringsArray"] = q

        if "searchStringsArray" not in input_data:
            raise ValueError("Missing search query for Google Places scraper. Provide 'search', 'query', or 'searchStringsArray'.")

        if "maxResults" not in input_data:
            input_data["maxResults"] = 20
        else:
            try:
                input_data["maxResults"] = int(input_data["maxResults"])
            except (ValueError, TypeError):
                input_data["maxResults"] = 20

    elif "instagram-scraper" in actor_id:
        urls = input_data.get("urls") or input_data.get("profiles") or input_data.get("directUrls") or input_data.get("search")
        if urls:
            if isinstance(urls, list):
                input_data["directUrls"] = urls
            else:
                input_data["directUrls"] = [urls]
        elif "directUrls" not in input_data:
            raise ValueError("Missing URLs for Instagram scraper. Provide 'urls', 'profiles', or 'directUrls'.")

    elif "facebook-pages-scraper" in actor_id:
        q = input_data.get("search") or input_data.get("query") or input_data.get("searchQueries")
        if q:
            if isinstance(q, list):
                input_data["searchQueries"] = q
            else:
                input_data["searchQueries"] = [q]
        elif "searchQueries" not in input_data:
            raise ValueError("Missing query for Facebook scraper. Provide 'search', 'query', or 'searchQueries'.")

    return input_data

def get_scrape_status() -> dict:
    """Returns the current Apify scrape status."""
    try:
        path = _status_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"current": {"status": "idle", "details": "No scrape jobs found"}}

def apify_leads(parameters: dict, **kwargs) -> str:
    token = _get_token()
    if not token:
        return "ERROR: Apify token not found in config/api_keys.json. Please provide an Apify API token."

    actor_id = parameters.get("actor_id")
    input_data = parameters.get("input_data", {})

    if not actor_id:
        return "ERROR: Missing actor_id."

    if actor_id not in _VALID_ACTORS:
        print(f"[Apify Warning] Actor '{actor_id}' is not in the validated list. Proceeding anyway.")

    try:
        input_data = _map_input(actor_id, input_data)
    except ValueError as e:
        return f"ERROR: Invalid input for actor '{actor_id}': {e}"

    print(f"[Apify] Starting actor {actor_id} in background thread with input: {input_data}")
    _set_status("running", f"Actor: {actor_id}, Query: {input_data}")

    t = threading.Thread(target=_run, args=(token, actor_id, input_data), daemon=True)
    t.start()

    return f"Apify actor '{actor_id}' iniciado em background. Os leads serao adicionados ao CRM automaticamente quando o scrape terminar."

def _run(token: str, actor_id: str, input_data: dict):
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            client = ApifyClient(token)
            run = client.actor(actor_id).call(run_input=input_data)
            results = list(client.dataset(run["defaultDatasetId"]).list_items().items)

            output_file = _base_dir() / "leads_results.json"
            output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

            added, dupes = 0, 0
            try:
                from actions.leads_manager import import_scraped_leads, get_db_lock
                with get_db_lock():
                    added, dupes = import_scraped_leads(results)
                print(f"[Apify] CRM Database updated: {added} new leads, {dupes} duplicates skipped.")
            except Exception as db_err:
                print(f"[Apify CRM Sync Error] {db_err}")
                _set_status("error", f"CRM sync failed: {db_err}")
                return

            _set_status("completed", f"{len(results)} leads scraped, {added} new, {dupes} duplicates")
            print(f"[Apify] Done: {len(results)} leads saved to leads_results.json.")
            return

        except Exception as e:
            error_msg = str(e)
            print(f"[Apify Retry {attempt}/{max_retries}] Error: {error_msg}")
            if attempt < max_retries:
                time.sleep(5 * attempt)
            else:
                _set_status("error", f"Failed after {max_retries} retries: {error_msg}")
                print(f"[Apify Thread Error] All retries exhausted: {error_msg}")
