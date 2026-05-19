import sounddevice as sd
import struct, math

SAMPLE_RATE = 16000
CHUNK = 800  # 50ms

def rms(data):
    count = len(data) // 2
    if count == 0: return 0.0
    samples = struct.unpack(f"<{count}h", data)
    return math.sqrt(sum(s*s for s in samples) / count) / 32768.0

print("Bata palmas e veja os valores de RMS (Ctrl+C para parar)...")
try:
    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
        while True:
            data, _ = stream.read(CHUNK)
            r = rms(bytes(data))
            if r > 0.01:
                print(f"RMS: {r:.4f}")
except Exception as e:
    print(f"Erro ao acessar o microfone: {e}")
