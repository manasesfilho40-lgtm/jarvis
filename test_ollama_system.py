import urllib.request
import json

def test():
    url = "http://127.0.0.1:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "llama3:8b",
        "system": "You are a pirate. Reply to everything in pirate speak.",
        "prompt": "Hello, how are you?",
        "stream": False
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            print("OLLAMA RESPONSE:", res_json.get("response"))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    test()
