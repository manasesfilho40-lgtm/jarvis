import sounddevice as sd
import struct, math, time

SAMPLE_RATE = 16000
CHUNK = 800

def rms(data):
    count = len(data) // 2
    if count == 0: return 0.0
    samples = struct.unpack(f"<{count}h", data)
    return math.sqrt(sum(s*s for s in samples) / count) / 32768.0

resultados = []
print("Iniciando escuta por 10 segundos...")
try:
    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK) as stream:
        start_time = time.time()
        while time.time() - start_time < 10:
            data, _ = stream.read(CHUNK)
            r = rms(bytes(data))
            if r > 0.005:
                resultados.append(f"{time.strftime('%H:%M:%S')} - RMS: {r:.4f}")
except Exception as e:
    resultados.append(f"Erro: {e}")

with open("resultado_teste.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(resultados))
