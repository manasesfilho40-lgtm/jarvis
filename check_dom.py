import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        
        # Test 1: Count .message-in
        msgs = await page.query_selector_all(".message-in")
        print(f"Count of .message-in: {len(msgs)}")
        
        if msgs:
            text_el = await msgs[-1].query_selector(".selectable-text")
            print(f"Has .selectable-text: {bool(text_el)}")
            if text_el:
                print("Text:", await text_el.inner_text())
                
        # Alternative approach: Find all elements with role="row" and see their text
        rows = await page.query_selector_all("div[role='row']")
        print(f"Count of role='row': {len(rows)}")
        if rows:
            last_row = rows[-1]
            print("Last row text:", await last_row.inner_text())

asyncio.run(check())
