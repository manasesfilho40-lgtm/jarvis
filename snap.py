import asyncio
from playwright.async_api import async_playwright

async def snap():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        contexts = browser.contexts
        if not contexts:
            print("No contexts found")
            return
        page = contexts[0].pages[0]
        await page.screenshot(path="wa_screen.png")
        print("Screenshot saved to wa_screen.png")

asyncio.run(snap())
