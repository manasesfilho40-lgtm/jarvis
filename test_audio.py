
import sounddevice as sd
print("Devices:")
print(sd.query_devices())
print("\nDefault Device:", sd.default.device)
