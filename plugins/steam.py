import asyncio
import logging
import shlex
import subprocess
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_steam")

try:
    import vdf
    HAS_VDF = True
except ImportError:
    HAS_VDF = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class SteamPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="steam",
                version="1.0.0",
                description="Steam integration - game library, launch, status",
            )
        super().__init__(manifest)
        self._api_key: str = ""
        self._steam_id: str = ""
        self._steam_path: str = ""
        self._games_cache: list[dict] = []

    async def on_load(self):
        self._api_key = self.config.get("steam_api_key", "")
        self._steam_id = self.config.get("steam_id", "")
        self._steam_path = self.config.get(
            "steam_path",
            "C:\\Program Files (x86)\\Steam\\steam.exe",
        )
        if self._api_key and self._steam_id and HAS_REQUESTS:
            try:
                summary = await self.get_player_summary()
                if summary:
                    logger.info(f"Steam plugin loaded - player: {summary.get('personaname', 'unknown')}")
                else:
                    logger.warning("Steam plugin loaded - could not fetch player summary")
            except Exception as e:
                logger.warning(f"Steam plugin loaded - API error: {e}")
        else:
            logger.info("Steam plugin loaded (limited - needs steam_api_key + steam_id)")

    async def on_unload(self):
        logger.info("Steam plugin unloaded")

    async def get_player_summary(self) -> Optional[dict]:
        if not self._api_key or not self._steam_id or not HAS_REQUESTS:
            return None
        try:
            url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            params = {"key": self._api_key, "steamids": self._steam_id}
            import requests
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            players = data.get("response", {}).get("players", [])
            return players[0] if players else None
        except Exception as e:
            logger.error(f"Failed to get player summary: {e}")
            return None

    async def get_owned_games(self) -> list[dict]:
        if not self._api_key or not self._steam_id or not HAS_REQUESTS:
            return self._games_cache
        try:
            url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
            params = {
                "key": self._api_key,
                "steamid": self._steam_id,
                "include_appinfo": True,
                "include_played_free_games": True,
                "format": "json",
            }
            import requests
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            games = data.get("response", {}).get("games", [])
            self._games_cache = [
                {
                    "appid": g["appid"],
                    "name": g.get("name", "Unknown"),
                    "playtime_hours": round(g.get("playtime_forever", 0) / 60, 1),
                    "img_icon_url": f"https://media.steampowered.com/steamcommunity/public/images/apps/{g['appid']}/{g.get('img_icon_url', '')}.jpg" if g.get("img_icon_url") else "",
                }
                for g in sorted(games, key=lambda x: x.get("playtime_forever", 0), reverse=True)
            ]
            return self._games_cache
        except Exception as e:
            logger.error(f"Failed to get owned games: {e}")
            return self._games_cache

    async def launch_game(self, appid_or_name: str) -> bool:
        if not self._steam_path:
            logger.error("Steam path not configured")
            return False
        try:
            cmd = f'"{self._steam_path}" -applaunch {shlex.quote(str(appid_or_name))}'
            subprocess.Popen(cmd, shell=True)
            logger.info(f"Launching Steam game: {appid_or_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to launch game: {e}")
            return False

    async def search_game(self, query: str) -> Optional[dict]:
        games = await self.get_owned_games()
        query_lower = query.lower().strip()
        for game in games:
            if query_lower in game["name"].lower():
                return game
        if HAS_REQUESTS:
            try:
                url = "https://api.steampowered.com/ISteamApps/GetAppList/v0002/"
                import requests
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                all_apps = data.get("applist", {}).get("apps", [])
                for app in all_apps:
                    name = app.get("name", "")
                    if query_lower in name.lower():
                        return {"appid": app["appid"], "name": name, "playtime_hours": 0}
            except Exception as e:
                logger.debug(f"Steam app list search failed: {e}")
        return None

    async def get_friends(self) -> list[dict]:
        if not self._api_key or not self._steam_id or not HAS_REQUESTS:
            return []
        try:
            url = "https://api.steampowered.com/ISteamUser/GetFriendList/v0001/"
            params = {"key": self._api_key, "steamid": self._steam_id, "relationship": "friend"}
            import requests
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            friends = data.get("friendslist", {}).get("friends", [])
            if not friends:
                return []
            friend_ids = [f["steamid"] for f in friends[:100]]
            summary_url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            summary_resp = requests.get(summary_url, params={"key": self._api_key, "steamids": ",".join(friend_ids)}, timeout=10)
            summary_resp.raise_for_status()
            players = summary_resp.json().get("response", {}).get("players", [])
            return [{"steamid": p["steamid"], "name": p.get("personaname", "Unknown"), "state": p.get("personastate", 0)} for p in players]
        except Exception as e:
            logger.error(f"Failed to get friends: {e}")
            return []


manifest = PluginManifest(
    name="steam",
    version="1.0.0",
    description="Steam integration - game library, launch, status",
)
