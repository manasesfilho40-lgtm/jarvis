import asyncio
import logging
import re
import time
from typing import Any, Optional

from agents.agent_base import BaseAgent
from core.event_bus import EventType, emit

logger = logging.getLogger("gaming_agent")


class GamingAgent(BaseAgent):
    def __init__(self):
        super().__init__("gaming", "Game detection, launch, and automation")
        self._known_games = {
            "steam": {
                "counter strike": "730",
                "cs:go": "730",
                "cs2": "730",
                "dota 2": "570",
                "elden ring": "1245620",
                "cyberpunk 2077": "1091500",
                "red dead redemption 2": "1174180",
                "baldur's gate 3": "1086940",
                "hogwarts legacy": "990080",
                "starfield": "1716740",
                "resident evil 4": "2050650",
                "spider-man": "1817070",
                "god of war": "1593500",
                "the witcher 3": "292030",
                "grand theft auto v": "271590",
                "gta v": "271590",
                "valorant": "valorant",
                "league of legends": "lol",
                "fortnite": "fortnite",
                "minecraft": "minecraft",
                "roblox": "roblox",
            }
        }
        self._game_processes = {}

    async def think(self, context: dict) -> Optional[dict]:
        return {"action": "idle", "agent": "gaming"}

    async def act(self, thought: dict) -> Any:
        return thought

    async def detect_running_games(self) -> list[str]:
        import psutil
        games = []
        game_keywords = [
            "steam", "epic", "origin", "ubisoft", "battlenet", "galaxy",
            "csgo", "cs2", "dota", "eldenring", "cyberpunk", "rdr2",
            "valheim", "minecraft", "roblox", "fortnite", "valorant",
            "lol", "league", "gta", "witcher", "bg3", "hogwarts",
        ]
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"].lower().replace(".exe", "")
                if any(kw in name for kw in game_keywords):
                    games.append(proc.info["name"])
            except Exception:
                continue
        return games

    async def launch_game(self, game_name: str, platform: str = "steam") -> bool:
        game_lower = game_name.lower().strip()

        if platform == "steam":
            app_id = None
            for alias, aid in self._known_games["steam"].items():
                if alias in game_lower or game_lower in alias:
                    app_id = aid
                    break

            if app_id:
                try:
                    import subprocess
                    steam_url = f"steam://run/{app_id}"
                    subprocess.Popen(["cmd", "/c", "start", steam_url], shell=True)
                    emit(EventType.APP_OPENED, {"game": game_name, "platform": "steam", "app_id": app_id}, source=self.name)
                    return True
                except Exception as e:
                    logger.error(f"Failed to launch {game_name}: {e}")
                    return False

        try:
            from actions.open_app import open_app
            result = open_app(parameters={"app_name": game_name}, player=None)
            return "Done" in str(result)
        except Exception as e:
            logger.error(f"Failed to launch {game_name}: {e}")
            return False

    async def get_game_status(self, game_name: str = "") -> dict:
        running = await self.detect_running_games()
        return {
            "running_games": running,
            "known_games": list(self._known_games.get("steam", {}).keys()),
            "game_running": any(g.lower().replace(".exe", "") in game_name.lower() for g in running) if game_name else False,
        }

    async def update_game(self, game_name: str = "") -> str:
        try:
            from actions.game_updater import game_updater
            params = {"action": "update", "platform": "steam"}
            if game_name:
                app_id = None
                for alias, aid in self._known_games["steam"].items():
                    if alias in game_name.lower():
                        app_id = aid
                        break
                if app_id:
                    params["app_id"] = app_id
            result = game_updater(parameters=params, player=None, speak=None)
            return str(result)
        except Exception as e:
            return f"Game update failed: {e}"

    async def observe(self, event) -> Optional[dict]:
        if event.type == EventType.USER_INPUT:
            text = event.data if isinstance(event.data, str) else ""
            game_keywords = ["jogar", "game", "steam", "epic", "abrir", "lançar", "rodar"]
            if any(kw in text.lower() for kw in game_keywords):
                for name in self._known_games["steam"]:
                    if name in text.lower():
                        return {"detected_game": name, "text": text}
        return None

    def subscribe_to_events(self):
        self.subscribe_to(EventType.USER_INPUT, EventType.APP_OPENED)


_gaming_agent_instance = None


def get_gaming_agent() -> GamingAgent:
    global _gaming_agent_instance
    if _gaming_agent_instance is None:
        _gaming_agent_instance = GamingAgent()
    return _gaming_agent_instance
