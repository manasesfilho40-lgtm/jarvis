import asyncio
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

logger = logging.getLogger("voice_pipeline")


try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False
    logger.warning("sounddevice not installed")


try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False


class STTEngine(Enum):
    WHISPER = "whisper"
    GEMINI = "gemini"
    FASTER_WHISPER = "faster_whisper"
    NONE = "none"


class TTSEngine(Enum):
    SAPI = "sapi"
    PIPER = "piper"
    EDGETTS = "edgetts"
    ESPEAK = "espeak"
    NONE = "none"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    dtype: str = "int16"
    silence_threshold: float = 800.0
    silence_duration: float = 1.5
    max_record_seconds: float = 30.0


@dataclass
class TranscriptionResult:
    text: str
    confidence: float = 0.0
    language: str = "pt"
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class SynthesisResult:
    success: bool = False
    duration_ms: float = 0.0
    error: str = ""


class VoicePipeline:
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self._stt_engine = STTEngine.NONE
        self._tts_engine = TTSEngine.NONE
        self._whisper_model = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._is_listening = False
        self._is_speaking = False
        self._on_transcription: Optional[Callable[[str], None]] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._vad = VoiceActivityDetector(
            threshold=self.config.silence_threshold,
            silence_frames=int(self.config.silence_duration * self.config.sample_rate / self.config.chunk_size),
        )

    def set_stt_engine(self, engine: STTEngine):
        self._stt_engine = engine
        if engine == STTEngine.WHISPER:
            self._init_whisper()
        logger.info(f"STT engine set to {engine.value}")

    def set_tts_engine(self, engine: TTSEngine):
        self._tts_engine = engine
        logger.info(f"TTS engine set to {engine.value}")

    def set_on_transcription(self, callback: Callable[[str], None]):
        self._on_transcription = callback

    def _init_whisper(self):
        try:
            from faster_whisper import WhisperModel
            self._whisper_model = WhisperModel("base", device="auto", compute_type="int8")
            logger.info("Whisper model loaded")
        except Exception as e:
            logger.error(f"Whisper init failed: {e}")
            self._stt_engine = STTEngine.NONE

    def start_listening(self):
        if self._is_listening:
            return
        if not HAS_SOUNDDEVICE:
            logger.error("sounddevice not available")
            return
        self._is_listening = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        logger.info("Voice listening started")

    def stop_listening(self):
        self._is_listening = False
        logger.info("Voice listening stopped")

    def _listen_loop(self):
        audio_buffer = []
        silence_frames = 0

        def callback(indata, frames, time_info, status):
            nonlocal silence_frames
            if self._is_speaking:
                return

            audio_arr = np.frombuffer(indata.tobytes(), dtype=np.int16)
            rms = np.sqrt(np.mean(audio_arr.astype(np.float32) ** 2)) if len(audio_arr) > 0 else 0

            if rms > self.config.silence_threshold:
                audio_buffer.append(audio_arr.copy())
                silence_frames = 0
            else:
                silence_frames += 1

        try:
            stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=self.config.dtype,
                blocksize=self.config.chunk_size,
                callback=callback,
            )
            stream.start()

            while self._is_listening:
                if audio_buffer and silence_frames > self._vad.silence_frames:
                    audio_np = np.concatenate(audio_buffer) if len(audio_buffer) > 1 else audio_buffer[0]
                    audio_buffer.clear()
                    silence_frames = 0

                    if len(audio_np) > 0:
                        text = self._transcribe(audio_np)
                        if text and self._on_transcription:
                            self._on_transcription(text)

                time.sleep(0.05)

            stream.stop()
            stream.close()
        except Exception as e:
            logger.error(f"Listen loop error: {e}")
        finally:
            self._is_listening = False

    def _transcribe(self, audio: np.ndarray) -> str:
        start = time.time()
        if self._stt_engine == STTEngine.WHISPER and self._whisper_model:
            try:
                audio_float = audio.astype(np.float32) / 32768.0
                segments, info = self._whisper_model.transcribe(audio_float, language="pt", beam_size=3)
                text = " ".join(seg.text for seg in segments).strip()
                logger.debug(f"Whisper: '{text[:60]}' ({len(audio)/self.config.sample_rate:.1f}s)")
                return text
            except Exception as e:
                logger.error(f"Whisper transcription failed: {e}")
                return ""
        return ""

    def set_piper_path(self, piper_exe: str = "", model_path: str = ""):
        self._piper_exe = piper_exe
        self._piper_model = model_path
        if piper_exe and os.path.exists(piper_exe):
            logger.info(f"Piper TTS configured: {piper_exe}")

    def set_wakeword(self, model_path: str = "", sensitivity: float = 0.5):
        self._wakeword_model = model_path
        self._wakeword_sensitivity = sensitivity
        self._wakeword_detected = threading.Event()
        if model_path and os.path.exists(model_path):
            logger.info(f"Wakeword model configured: {model_path}")

    def wait_for_wakeword(self, timeout: float = None) -> bool:
        if not hasattr(self, '_wakeword_model') or not self._wakeword_model:
            return True
        return self._wakeword_detected.wait(timeout=timeout)

    def speak(self, text: str, wait: bool = True) -> SynthesisResult:
        start = time.time()
        self._is_speaking = True

        try:
            if self._tts_engine == TTSEngine.SAPI:
                self._speak_sapi(text)
            elif self._tts_engine == TTSEngine.PIPER:
                self._speak_piper(text, wait)
            elif self._tts_engine == TTSEngine.EDGETTS:
                self._speak_edgetts(text, wait)
            elif self._tts_engine == TTSEngine.ESPEAK:
                self._speak_espeak(text)
            elif self._tts_engine == TTSEngine.NONE:
                logger.debug(f"TTS disabled, would say: {text[:60]}")
            else:
                logger.warning(f"TTS engine {self._tts_engine} not implemented")
                self._speak_sapi(text)

            return SynthesisResult(
                success=True,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return SynthesisResult(success=False, error=str(e))
        finally:
            self._is_speaking = False

    def _speak_sapi(self, text: str):
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            try:
                for v in speaker.GetVoices():
                    lang_id = v.Id.lower() if hasattr(v, "Id") else ""
                    desc = v.GetDescription().lower() if hasattr(v, "GetDescription") else ""
                    if "language=416" in lang_id or "language=816" in lang_id or "portug" in desc:
                        speaker.Voice = v
                        break
            except Exception:
                pass
            speaker.Speak(text)
        except Exception as e:
            logger.error(f"SAPI TTS failed: {e}")
            raise

    def _speak_piper(self, text: str, wait: bool = True):
        piper_exe = getattr(self, '_piper_exe', "piper.exe")
        model = getattr(self, '_piper_model', "voice.onnx")
        if not os.path.exists(piper_exe):
            logger.warning(f"Piper not found at {piper_exe}, falling back to SAPI")
            self._speak_sapi(text)
            return
        try:
            proc = subprocess.Popen(
                [piper_exe, "--model", model, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            stdout, _ = proc.communicate(input=text.encode("utf-8"), timeout=30)
            if stdout and HAS_SOUNDFILE:
                import io
                data, sr = sf.read(io.BytesIO(stdout), dtype="int16")
                sd.play(data, sr)
                if wait:
                    sd.wait()
        except Exception as e:
            logger.error(f"Piper TTS failed: {e}")
            self._speak_sapi(text)

    def _speak_edgetts(self, text: str, wait: bool = True):
        try:
            import edge_tts
            import tempfile
            communicate = edge_tts.Communicate(text, voice="pt-BR-AntonioNeural")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name
            asyncio.run(communicate.save(temp_path))
            if HAS_SOUNDFILE:
                data, sr = sf.read(temp_path, dtype="int16")
                sd.play(data, sr)
                if wait:
                    sd.wait()
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"EdgeTTS failed: {e}")
            self._speak_sapi(text)

    def _speak_espeak(self, text: str):
        try:
            subprocess.run(
                ["espeak", "-v", "pt-br", text],
                capture_output=True, timeout=30,
            )
        except Exception as e:
            logger.error(f"eSpeak failed: {e}")
            self._speak_sapi(text)

    async def speak_async(self, text: str) -> SynthesisResult:
        return await asyncio.to_thread(self.speak, text, True)

    def is_busy(self) -> bool:
        return self._is_listening or self._is_speaking

    def get_status(self) -> dict:
        return {
            "listening": self._is_listening,
            "speaking": self._is_speaking,
            "stt_engine": self._stt_engine.value,
            "tts_engine": self._tts_engine.value,
            "sample_rate": self.config.sample_rate,
        }

    def close(self):
        self.stop_listening()
        self._whisper_model = None

    def __repr__(self):
        return f"VoicePipeline(stt={self._stt_engine.value}, tts={self._tts_engine.value})"


class VoiceActivityDetector:
    def __init__(self, threshold: float = 800.0, silence_frames: int = 50):
        self.threshold = threshold
        self.silence_frames = silence_frames

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
        return rms > self.threshold


_pipeline_instance = None


def get_pipeline(config: Optional[AudioConfig] = None) -> VoicePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = VoicePipeline(config)
    return _pipeline_instance
