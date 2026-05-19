import json
import os
from pathlib import Path
from apify_client import ApifyClient

def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent

def _get_token() -> str:
    try:
        cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        return cfg.get("apify_token", "")
    except Exception:
        return ""

def _map_input(actor_id: str, input_data: dict) -> dict:
    """Conserta inputs comuns para facilitar a vida da IA."""
    if "crawler-google-places" in actor_id:
        # Se mandou "search" ou "query" ao invés de searchStringsArray
        q = input_data.get("search") or input_data.get("query") or input_data.get("location")
        if q and "searchStringsArray" not in input_data:
            input_data["searchStringsArray"] = [q] if isinstance(q, str) else q
        
        # Garante o campo maxResults se não existir
        if "maxResults" not in input_data:
            input_data["maxResults"] = 20

    return input_data

def apify_leads(parameters: dict, **kwargs) -> str:
    """
    Scrape leads using Apify Actors.
    """
    token = _get_token()
    if not token:
        return "ERROR: Apify token not found in config/api_keys.json. Please provide an Apify API token."

    actor_id = parameters.get("actor_id")
    input_data = parameters.get("input_data", {})

    if not actor_id:
        return "ERROR: Missing actor_id."

    # Aplica o mapeamento inteligente
    input_data = _map_input(actor_id, input_data)

    client = ApifyClient(token)
    
    print(f"[Apify] Running actor {actor_id} with input: {input_data}")
    try:
        # Start the actor and wait for it to finish
        run = client.actor(actor_id).call(run_input=input_data)
        
        # Fetch results from the dataset
        results = list(client.dataset(run["defaultDatasetId"]).list_items().items)
        
        output_file = _base_dir() / "leads_results.json"
        output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Import to structured CRM database (new vs used)
        try:
            from actions.leads_manager import import_scraped_leads
            added, dupes = import_scraped_leads(results)
            summary = f"Successfully found {len(results)} leads using {actor_id}.\n"
            summary += f"CRM Database updated: {added} new leads added, {dupes} duplicates skipped.\n"
            summary += f"Results saved to {output_file.name}."
        except Exception as db_err:
            print(f"[Apify CRM Sync Error] {db_err}")
            summary = f"Successfully found {len(results)} leads using {actor_id}.\n"
            summary += f"Results saved to {output_file.name}."
        
        # Return a snippet of the results to the AI
        snippet = results[:5]
        return f"{summary}\n\nTop 5 results preview:\n{json.dumps(snippet, indent=2, ensure_ascii=False)}"

    except Exception as e:
        return f"ERROR running Apify actor: {e}"
