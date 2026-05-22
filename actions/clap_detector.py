"""
Clap Detector for JARVIS Mark XXXIX
====================================
Detects double-clap patterns to toggle JARVIS mute/unmute.
Uses a separate low-priority audio analysis (does not interfere
with the main mic stream).

How it works:
  1. Continuously reads small chunks from the microphone
  2. Measures RMS amplitude of each chunk
  3. When amplitude exceeds a threshold → registers a "clap"
  4. Two claps within a short window → triggers toggle
  5. Cooldown prevents rapid re-triggers
"""

from __future__ import annotations

import math
import struct
import threading
import time
from typing import Callable

import sounddevice as sd
from pathlib import Path


class ClapDetector:
    """
    Listens for double-clap patterns on the microphone.

    Parameters
    ----------
    on_clap : callable
        Function to call when a valid double-clap is detected.
    threshold : float
        RMS amplitude threshold to consider a sound a "clap".
        Higher = less sensitive (needs louder claps).
        Default 0.35 works well for most environments.
    double_clap_window : float
        Max seconds between two claps to count as a double-clap.
    cooldown : float
        Seconds to wait after a trigger before accepting new claps.
    sample_rate : int
        Audio sample rate (default 16000 Hz).
    chunk_ms : int
        Length of each audio chunk in milliseconds.
    """

    def __init__(
        self,
        on_clap: Callable[[], None],
        threshold: float = 0.02,
        double_clap_window: float = 1.0,
        cooldown: float = 1.5,
        sample_rate: int = 16000,
        chunk_ms: int = 50,
    ):
        self.on_clap = on_clap
        self.threshold = threshold
        self.double_clap_window = double_clap_window
        self.cooldown = cooldown
        self.sample_rate = sample_rate
        self.chunk_size = int(sample_rate * chunk_ms / 1000)

        self._running = False
        self._thread: threading.Thread | None = None
        self._last_clap_time: float = 0.0
        self._last_trigger_time: float = 0.0
        self._clap_count = 0
        self._enabled = True
        self._prev_rms = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def start(self):
        """Start listening for claps in background thread."""
        if self._running:
            return
        self._running = True
        # Do not start _listen_loop thread to avoid opening a second mic stream
        # self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        # self._thread.start()

    def stop(self):
        """Stop listening."""
        self._running = False

    def process_audio_chunk(self, raw: bytes):
        """Process a chunk of audio data externally (passive mode)."""
        if not self._enabled:
            self._prev_rms = 0.0
            return

        rms = self._rms(raw)
        now = time.time()

        # Check cooldown
        if now - self._last_trigger_time < self.cooldown:
            self._prev_rms = rms
            return

        if self._is_clap(rms, self._prev_rms):
            time_since_last = now - self._last_clap_time
            self._log(f"[ClapDetector] 👏 Palma! (Contagem: {self._clap_count + 1}) RMS={rms:.4f}")

            if time_since_last < self.double_clap_window and self._clap_count >= 1:
                # Double clap detected!
                self._log("[ClapDetector] ✨ Dupla palma detectada! DISPARANDO...")
                self._clap_count = 0
                self._last_trigger_time = now
                try:
                    self.on_clap()
                except Exception as e:
                    self._log(f"[ClapDetector] Erro no callback: {e}")
            else:
                # First clap
                self._clap_count = 1
                self._last_clap_time = now

        # Reset clap count if window expired
        if now - self._last_clap_time > self.double_clap_window:
            if self._clap_count > 0:
                self._clap_count = 0

        self._prev_rms = rms

    def _rms(self, data: bytes) -> float:
        """Calculate Root Mean Square of audio data (int16)."""
        count = len(data) // 2
        if count == 0:
            return 0.0
        fmt = f"<{count}h"
        try:
            samples = struct.unpack(fmt, data)
            sum_sq = sum(s * s for s in samples)
            return math.sqrt(sum_sq / count) / 32768.0
        except Exception:
            return 0.0

    def _is_clap(self, rms: float, prev_rms: float) -> bool:
        """
        Detect a clap: sudden spike in amplitude.
        """
        if rms > self.threshold:
            # print(f"[DEBUG] Pico detectado: {rms:.4f} (Threshold: {self.threshold})")
            return rms > prev_rms * 2.0
        return False

    def _log(self, message: str):
        try:
            print(message)
        except Exception:
            pass
        try:
            log_path = Path(__file__).resolve().parent.parent / "clap_detector.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except:
            pass

    def _listen_loop(self):
        """Main listening loop running in background thread."""
        prev_rms = 0.0
        self._log(f"[ClapDetector] Iniciando loop de escuta...")

        while self._running:
            try:
                # Tenta abrir o dispositivo padrão dentro do loop para recuperação de erros
                with sd.RawInputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.chunk_size,
                ) as stream:
                    self._log(f"[ClapDetector] Ouvindo com threshold={self.threshold}...")
                    while self._running:
                        try:
                            data, _ = stream.read(self.chunk_size)
                            raw = bytes(data)
                        except Exception as e:
                            self._log(f"[ClapDetector] Erro na leitura (reconfigurando stream): {e}")
                            break # Sai do stream para recriá-lo no próximo ciclo

                        if not self._enabled:
                            prev_rms = 0.0
                            time.sleep(0.2)
                            continue

                        rms = self._rms(raw)
                        now = time.time()

                        # Check cooldown
                        if now - self._last_trigger_time < self.cooldown:
                            prev_rms = rms
                            continue

                        if self._is_clap(rms, prev_rms):
                            time_since_last = now - self._last_clap_time
                            self._log(f"[ClapDetector] 👏 Palma! (Contagem: {self._clap_count + 1}) RMS={rms:.4f}")

                            if time_since_last < self.double_clap_window and self._clap_count >= 1:
                                # Double clap detected!
                                self._log("[ClapDetector] ✨ Dupla palma detectada! DISPARANDO...")
                                self._clap_count = 0
                                self._last_trigger_time = now
                                try:
                                    self.on_clap()
                                except Exception as e:
                                    self._log(f"[ClapDetector] Erro no callback: {e}")
                            else:
                                # First clap
                                self._clap_count = 1
                                self._last_clap_time = now

                        # Reset clap count if window expired
                        if now - self._last_clap_time > self.double_clap_window:
                            if self._clap_count > 0:
                                self._clap_count = 0

                        prev_rms = rms
            except Exception as e:
                self._log(f"[ClapDetector] Erro ao iniciar stream: {e}")
            
            if self._running:
                time.sleep(1.0) # Espera 1s antes de tentar reconectar o dispositivo

        self._running = False
