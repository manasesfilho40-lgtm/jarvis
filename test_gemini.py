import json
from google import genai
from pathlib import Path

def test():
    try:
        with open("config/api_keys.json", "r") as f:
            key = json.load(f)["gemini_api_key"]
        
        client = genai.Client(api_key=key)
        res = client.models.generate_content(
            model="gemini-1.5-flash",
            contents="Hello"
        )
        print("SUCCESS:", res.text)
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    test()
