import numpy as np
from faster_whisper import WhisperModel

class LocalSTT:
    def __init__(self, model_size="base", device="auto"):
        self.model_size = model_size
        self.sample_rate = 16000
        print(f"[LocalSTT] Carregando whisper {model_size}...")
        try:
            self.model = WhisperModel(model_size, device=device, compute_type="int8")
            print(f"[LocalSTT] Whisper {model_size} pronto (device: {self.model.device})")
        except Exception as e:
            print(f"[LocalSTT] Erro ao carregar {model_size}: {e}")
            print("[LocalSTT] Tentando device=cpu...")
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print(f"[LocalSTT] Whisper {model_size} pronto (cpu)")

    def transcribe(self, audio_np: np.ndarray) -> str:
        if len(audio_np) == 0:
            return ""
        try:
            segments, info = self.model.transcribe(audio_np, language="pt", beam_size=3)
            text = " ".join(seg.text for seg in segments)
            return text.strip()
        except Exception as e:
            print(f"[LocalSTT] Erro na transcrição: {e}")
            return ""
