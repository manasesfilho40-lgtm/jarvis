import asyncio
import json
import traceback
from google import genai
from google.genai import types

async def main():
    with open('config/api_keys.json', 'r') as f:
        api_key = json.load(f)['gemini_api_key']
    
    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"]
    )
    
    try:
        async with client.aio.live.connect(
            model='models/gemini-3.1-flash-live-preview',
            config=config
        ) as session:
            print("Connected successfully!")
            await asyncio.sleep(2)
            async for response in session.receive():
                print("Received response!")
                break
    except Exception as e:
        print("Error:", type(e).__name__, str(e))
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
