import asyncio
import logging
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_notion")

try:
    from notion_client import Client
    HAS_NOTION = True
except ImportError:
    HAS_NOTION = False


class NotionPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="notion",
                version="1.0.0",
                description="Notion API integration - pages, databases, search",
            )
        super().__init__(manifest)
        self._client: Any = None
        self._token: str = ""

    async def on_load(self):
        self._token = self.config.get("notion_token", "")
        if self._token and HAS_NOTION:
            try:
                self._client = Client(auth=self._token)
                me = self._client.users.me()
                logger.info(f"Notion plugin loaded - user: {me.get('name', 'unknown')}")
            except Exception as e:
                logger.warning(f"Notion auth failed: {e}")
        elif HAS_NOTION:
            logger.info("Notion plugin loaded (no token)")
        else:
            logger.warning("Notion plugin loaded - notion-client not installed. Install: pip install notion-client")

    async def on_unload(self):
        logger.info("Notion plugin unloaded")

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not self._client:
            return []
        try:
            results = self._client.search(query=query, page_size=limit)
            items = []
            for r in results.get("results", []):
                obj_type = r.get("object", "")
                props = r.get("properties", {})
                title = ""
                if obj_type == "page":
                    for prop in props.values():
                        if prop.get("type") == "title":
                            title_parts = prop.get("title", [])
                            title = "".join(t.get("plain_text", "") for t in title_parts)
                            break
                elif obj_type == "database":
                    title_parts = r.get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                items.append({
                    "id": r["id"],
                    "type": obj_type,
                    "title": title or "Untitled",
                    "url": r.get("url", ""),
                    "created_time": r.get("created_time", ""),
                })
            return items
        except Exception as e:
            logger.error(f"Notion search failed: {e}")
            return []

    async def create_page(self, parent_id: str, title: str, content: str = "") -> Optional[dict]:
        if not self._client:
            return None
        try:
            children = []
            if content:
                for line in content.split("\n"):
                    if line.strip():
                        children.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": line[:2000]}}]
                            },
                        })
            page = self._client.pages.create(
                parent={"page_id": parent_id},
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": title[:100]}}]
                    }
                },
                children=children if children else None,
            )
            logger.info(f"Notion page created: {title}")
            return {"id": page["id"], "title": title, "url": page.get("url", "")}
        except Exception as e:
            logger.error(f"Failed to create Notion page: {e}")
            return None

    async def query_database(self, database_id: str, filter_dict: dict = None, limit: int = 20) -> list[dict]:
        if not self._client:
            return []
        try:
            body = {"page_size": limit}
            if filter_dict:
                body["filter"] = filter_dict
            results = self._client.databases.query(database_id=database_id, **body)
            items = []
            for r in results.get("results", []):
                props = r.get("properties", {})
                row = {"id": r["id"], "url": r.get("url", "")}
                for prop_name, prop_data in props.items():
                    ptype = prop_data.get("type", "")
                    if ptype == "title":
                        title_parts = prop_data.get("title", [])
                        row["title"] = "".join(t.get("plain_text", "") for t in title_parts)
                    elif ptype == "rich_text":
                        text_parts = prop_data.get("rich_text", [])
                        row[prop_name] = "".join(t.get("plain_text", "") for t in text_parts)
                    elif ptype == "select":
                        select = prop_data.get("select")
                        row[prop_name] = select.get("name", "") if select else ""
                    elif ptype == "status":
                        status = prop_data.get("status")
                        row[prop_name] = status.get("name", "") if status else ""
                    elif ptype == "date":
                        date = prop_data.get("date")
                        row[prop_name] = date.get("start", "") if date else ""
                    elif ptype == "checkbox":
                        row[prop_name] = prop_data.get("checkbox", False)
                    elif ptype == "number":
                        row[prop_name] = prop_data.get("number")
                items.append(row)
            return items
        except Exception as e:
            logger.error(f"Failed to query Notion database: {e}")
            return []


manifest = PluginManifest(
    name="notion",
    version="1.0.0",
    description="Notion API integration - pages, databases, search",
)
