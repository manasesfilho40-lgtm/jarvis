import json
from google import genai

def test():
    try:
        with open("config/api_keys.json", "r") as f:
            key = json.load(f)["gemini_api_key"]
        
        client = genai.Client(api_key=key)
        res = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Hello"
        )
        print("SUCCESS:", res.text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("ERROR:", e)

if __name__ == "__main__":
    test()
