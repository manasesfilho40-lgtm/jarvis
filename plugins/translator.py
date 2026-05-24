import asyncio
import logging
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_translator")


class TranslatorPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="translator",
                version="1.0.0",
                description="Translation between languages using free APIs",
            )
        super().__init__(manifest)
        self._default_target = "pt"
        self._default_source = "auto"

    async def on_load(self):
        self._default_target = self.config.get("default_target_lang", "pt")
        self._default_source = self.config.get("default_source_lang", "auto")
        logger.info(f"Translator plugin loaded (default: {self._default_source} -> {self._default_target})")

    async def on_unload(self):
        logger.info("Translator plugin unloaded")

    async def translate(self, text: str, target_lang: str = "", source_lang: str = "") -> Optional[str]:
        target = target_lang or self._default_target
        source = source_lang or self._default_source
        try:
            import requests
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": source,
                "tl": target,
                "dt": "t",
                "q": text,
            }
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            translated = "".join(part[0] for part in data[0] if part[0])
            detected = data[2] if len(data) > 2 and data[2] else source
            logger.info(f"Translated [{detected}->{target}]: {text[:50]}...")
            return translated
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return None

    async def detect_language(self, text: str) -> Optional[str]:
        try:
            import requests
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": "auto",
                "tl": "en",
                "dt": "t",
                "q": text[:100],
            }
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            detected = data[2] if len(data) > 2 and data[2] else None
            return detected
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return None

    async def get_supported_languages(self) -> dict:
        return {
            "pt": "Portuguese",
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "ru": "Russian",
            "ar": "Arabic",
            "nl": "Dutch",
            "pl": "Polish",
            "sv": "Swedish",
        }


manifest = PluginManifest(
    name="translator",
    version="1.0.0",
    description="Translation between languages using free Google Translate API",
)
