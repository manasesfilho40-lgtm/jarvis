import asyncio
import logging
from typing import Any, Callable, Optional

from agents.agent_base import BaseAgent
from core.event_bus import EventType, emit
from voice.voice_pipeline import (
    STTEngine, TTSEngine, VoicePipeline, get_pipeline,
)

logger = logging.getLogger("voice_agent")


class VoiceAgent(BaseAgent):
    def __init__(self):
        super().__init__("voice", "Speech-to-text and text-to-speech voice pipeline")
        self._pipeline: Optional[VoicePipeline] = None
        self._listening = False
        self._on_voice_command: Optional[Callable[[str], None]] = None

    def set_on_voice_command(self, callback: Callable[[str], None]):
        self._on_voice_command = callback

    async def think(self, context: dict) -> Optional[dict]:
        if self._pipeline is None:
            self._pipeline = get_pipeline()
            self._pipeline.set_on_transcription(self._handle_transcription)
        return {"action": "check_status", "listening": self._listening}

    async def act(self, thought: dict) -> Any:
        return thought

    def _handle_transcription(self, text: str):
        if text:
            logger.info(f"Voice input: {text[:60]}")
            emit(EventType.VOICE_INPUT, {"text": text}, source=self.name)
            if self._on_voice_command:
                self._on_voice_command(text)

    def start_listening(self):
        if self._pipeline is None:
            self._pipeline = get_pipeline()
            self._pipeline.set_on_transcription(self._handle_transcription)
        self._pipeline.set_stt_engine(STTEngine.WHISPER)
        self._pipeline.set_tts_engine(TTSEngine.SAPI)
        self._pipeline.start_listening()
        self._listening = True
        emit(EventType.VOICE_INPUT, {"action": "started_listening"}, source=self.name)
        logger.info("Voice agent listening started")

    def stop_listening(self):
        if self._pipeline:
            self._pipeline.stop_listening()
        self._listening = False
        logger.info("Voice agent listening stopped")

    def speak(self, text: str, wait: bool = True):
        if self._pipeline:
            result = self._pipeline.speak(text, wait=wait)
            if result.success:
                emit(EventType.VOICE_OUTPUT, {"text": text[:60]}, source=self.name)
            return result
        return None

    async def speak_async(self, text: str):
        if self._pipeline:
            result = await self._pipeline.speak_async(text)
            return result
        return None

    def set_stt_engine(self, engine: STTEngine):
        if self._pipeline:
            self._pipeline.set_stt_engine(engine)

    def set_tts_engine(self, engine: TTSEngine):
        if self._pipeline:
            self._pipeline.set_tts_engine(engine)

    def get_status(self) -> dict:
        if self._pipeline:
            status = self._pipeline.get_status()
            status["agent_active"] = self.status
            return status
        return {"agent_active": self.status.value}

    def close(self):
        self.stop_listening()
        if self._pipeline:
            self._pipeline.close()

    async def observe(self, event) -> Optional[dict]:
        return None


_voice_agent_instance = None


def get_voice_agent() -> VoiceAgent:
    global _voice_agent_instance
    if _voice_agent_instance is None:
        _voice_agent_instance = VoiceAgent()
    return _voice_agent_instance
