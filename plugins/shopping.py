import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote, urlparse

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_shopping")


class ShoppingPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="shopping",
                version="1.0.0",
                description="Shopping - search products with free shipping and promotions on Mercado Livre, Magazine Luiza, Amazon Brasil",
                tags=["shopping", "ecommerce", "products", "brazil"],
            )
        super().__init__(manifest)
        self._max_results = 10
        self._browser = None
        self._playwright = None

    async def on_load(self):
        self._max_results = int(self.config.get("max_results", 10))
        logger.info(f"Shopping plugin loaded (max_results: {self._max_results})")

    async def on_unload(self):
        await self._close_browser()
        logger.info("Shopping plugin unloaded")

    async def _get_browser(self):
        if self._browser:
            return self._browser
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            return self._browser
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise

    async def _close_browser(self):
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    async def _new_page(self):
        browser = await self._get_browser()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 KHTML, like Gecko Chrome/131.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)
        return page, context

    async def search_products(
        self,
        query: str,
        max_price: Optional[float] = None,
        free_shipping: bool = True,
        promotion: bool = True,
        store: str = "mercadolivre",
    ) -> list[dict]:
        store_map = {
            "mercadolivre": self._search_mercadolivre,
            "magazineluiza": self._search_magazineluiza,
            "amazon": self._search_amazon,
        }
        searcher = store_map.get(store, self._search_mercadolivre)
        try:
            results = await searcher(query, max_price, free_shipping, promotion)
            return results[:self._max_results]
        except Exception as e:
            logger.error(f"Shopping search failed ({store}): {e}")
            return [{"error": f"Falha ao buscar em {store}: {str(e)}"}]

    async def search_all_stores(
        self,
        query: str,
        max_price: Optional[float] = None,
        free_shipping: bool = True,
        promotion: bool = True,
    ) -> dict[str, list[dict]]:
        stores = ["mercadolivre", "magazineluiza", "amazon"]
        tasks = []
        for store in stores:
            tasks.append(self.search_products(query, max_price, free_shipping, promotion, store))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = {}
        for i, store in enumerate(stores):
            if isinstance(results[i], Exception):
                output[store] = [{"error": str(results[i])}]
            else:
                output[store] = results[i]
        return output

    async def _search_mercadolivre(
        self, query: str, max_price: Optional[float], free_shipping: bool, promotion: bool
    ) -> list[dict]:
        page, context = None, None
        for attempt in range(3):
            try:
                page, context = await self._new_page()
                url = f"https://lista.mercadolivre.com.br/{quote(query)}"
                await page.goto(url, wait_until="load", timeout=45000)
                await asyncio.sleep(3)
                try:
                    await page.wait_for_selector("li.ui-search-layout__item", timeout=10000)
                except Exception:
                    await asyncio.sleep(3)
                items = await page.evaluate("""
                    () => {
                        const cards = document.querySelectorAll('li.ui-search-layout__item');
                        return Array.from(cards).slice(0, 25).map(card => {
                            const titleEl = card.querySelector('.poly-component__title');
                            const priceEl = card.querySelector('.andes-money-amount__fraction');
                            const centsEl = card.querySelector('.andes-money-amount__cents');
                            const oldPriceEl = card.querySelector(
                                '.andes-money-amount--previous .andes-money-amount__fraction'
                            );
                            const discountEl = card.querySelector('.andes-money-amount__discount');
                            const linkEl = card.querySelector('.poly-component__title');
                            const imageEl = card.querySelector('.poly-component__picture');
                            const fullText = card.textContent || '';
                            const hasFreeShipping = /frete\\s*gr(at|a)tis/i.test(fullText);
                            const hasDiscount = /(\\d+%\\s*off|desconto|promo)/i.test(fullText);
                            return {
                                title: titleEl ? titleEl.textContent.trim() : '',
                                url: linkEl ? linkEl.href : '',
                                price_text: priceEl ? priceEl.textContent.trim() : '',
                                cents: centsEl ? centsEl.textContent.trim() : '00',
                                old_price_text: oldPriceEl ? oldPriceEl.textContent.trim() : '',
                                discount_text: discountEl ? discountEl.textContent.trim() : '',
                                image: imageEl ? (imageEl.src || '') : '',
                                has_free_shipping: hasFreeShipping,
                                has_discount_tag: hasDiscount,
                            };
                        });
                    }
                """)
                seen = set()
                results = []
                for item in items:
                    try:
                        title = item["title"]
                        if not title or len(title) < 5 or title in seen:
                            continue
                        price = self._parse_brl(item["price_text"] + "." + item.get("cents", "00"))
                        if price <= 0:
                            continue
                        old_price = self._parse_brl(item["old_price_text"])
                        has_discount = old_price > 0 and price < old_price * 0.99
                        promo = has_discount or item["has_discount_tag"]
                        ship_free = item["has_free_shipping"]
                        if promotion and not promo:
                            continue
                        if free_shipping and not ship_free:
                            continue
                        if max_price and price > max_price:
                            continue
                        seen.add(title)
                        results.append({
                            "title": title, "url": item["url"],
                            "price": price, "old_price": old_price if old_price > 0 else None,
                            "discount": item["discount_text"],
                            "has_discount": has_discount, "promotion_tag": promo,
                            "free_shipping": ship_free, "installments": "", "rating": "", "reviews": "",
                            "store": "Mercado Livre", "image": item["image"], "source": "mercadolivre",
                        })
                    except Exception:
                        continue
                return results
            except Exception as e:
                logger.warning(f"ML attempt {attempt + 1} failed: {e}")
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    context = None
                if attempt < 2:
                    await asyncio.sleep(2)
                continue
        return []


    async def _search_magazineluiza(
        self, query: str, max_price: Optional[float], free_shipping: bool, promotion: bool
    ) -> list[dict]:
        page, context = None, None
        try:
            page, context = await self._new_page()
            url = f"https://www.magazineluiza.com.br/busca/{quote(query)}/"
            await page.goto(url, wait_until="load", timeout=45000)
            await asyncio.sleep(4)
            title = await page.title()
            if "nao e possivel" in title.lower() or "nao foi possivel" in title.lower():
                logger.warning("Magazine Luiza blocked our request")
                return []
            items = await page.evaluate("""
                () => {
                    const cards = document.querySelectorAll(
                        '[data-testid=product-card], .product-card, ' +
                        'div[class*=card], article[class*=product]'
                    );
                    return Array.from(cards).slice(0, 25).map(card => {
                        const titleEl = card.querySelector('h2, [class*=title], [data-testid=product-title]');
                        const linkEl = card.querySelector('a[href*=\"/produto/\"]');
                        const priceEl = card.querySelector('[class*=price], [data-testid=price-value]');
                        const oldPriceEl = card.querySelector('s, [class*=old], [data-testid=list-price]');
                        const imageEl = card.querySelector('img[src*=\"http\"]');
                        const fullText = card.textContent || '';
                        const hasFreeShipping = /frete\\s*gr(a|a)tis/i.test(fullText);
                        const hasDiscount = /(\\d+%\\s*off|desconto|promo|\\d+%|por tempo limitado)/i.test(fullText);
                        return {
                            title: titleEl ? titleEl.textContent.trim() : '',
                            url: linkEl ? linkEl.href : '',
                            price_text: priceEl ? priceEl.textContent.trim() : '',
                            old_price_text: oldPriceEl ? oldPriceEl.textContent.trim() : '',
                            image: imageEl ? imageEl.src : '',
                            has_free_shipping: hasFreeShipping,
                            has_discount_tag: hasDiscount,
                        };
                    });
                }
            """)

            seen_titles = set()
            results = []
            for item in items:
                try:
                    title = item["title"]
                    if not title or len(title) < 5:
                        continue
                    if title in seen_titles:
                        continue
                    price = self._parse_brl(item["price_text"])
                    if price <= 0:
                        continue
                    old_price = self._parse_brl(item["old_price_text"])
                    has_discount = old_price > 0 and price < old_price * 0.99
                    promo = has_discount or item["has_discount_tag"]
                    ship_free = item["has_free_shipping"]
                    if promotion and not promo:
                        continue
                    if free_shipping and not ship_free:
                        continue
                    if max_price and price > max_price:
                        continue
                    seen_titles.add(title)
                    u = item["url"]
                    if u and u.startswith("/"):
                        u = "https://www.magazineluiza.com.br" + u
                    results.append({
                        "title": title,
                        "url": u,
                        "price": price,
                        "old_price": old_price if old_price > 0 else None,
                        "discount": "",
                        "has_discount": has_discount,
                        "promotion_tag": promo,
                        "free_shipping": ship_free,
                        "installments": "",
                        "rating": "",
                        "store": "Magazine Luiza",
                        "image": item["image"],
                        "source": "magazineluiza",
                    })
                except Exception as e:
                    logger.warning(f"Parse Magalu item error: {e}")
                    continue
            return results
        except Exception as e:
            logger.error(f"Magazine Luiza search error: {e}")
            return []
        finally:
            if context:
                await context.close()

    async def _search_amazon(
        self, query: str, max_price: Optional[float], free_shipping: bool, promotion: bool
    ) -> list[dict]:
        page, context = None, None
        try:
            page, context = await self._new_page()
            url = f"https://www.amazon.com.br/s?k={quote(query)}"
            await page.goto(url, wait_until="load", timeout=45000)
            await asyncio.sleep(4)
            items = await page.evaluate("""
                () => {
                    const cards = document.querySelectorAll(
                        '[data-component-type=s-search-result], .s-result-item, ' +
                        'div[data-asin], .puis-card-container'
                    );
                    return Array.from(cards).slice(0, 25).map(card => {
                        const linkEl = card.querySelector('a > h2');
                        const titleEl = card.querySelector('h2 span, h2');
                        const priceEl = card.querySelector('.a-price .a-offscreen, .a-price-whole');
                        const oldPriceEl = card.querySelector(
                            '.a-text-price span[aria-hidden=true]'
                        );
                        const imageEl = card.querySelector('img.s-image');
                        const ratingEl = card.querySelector(
                            'i.a-icon-star-small span.a-icon-alt, i.a-icon-star span.a-icon-alt'
                        );
                        const fullText = card.textContent || '';
                        const hasPrime = /prime/i.test(fullText);
                        const hasDiscount = /(\\d+%|cupom|coupon|promo)/i.test(fullText);
                        return {
                            title: titleEl ? titleEl.textContent.trim() : '',
                            url: linkEl && linkEl.parentElement ? linkEl.parentElement.href : '',
                            price_text: priceEl ? priceEl.textContent.trim() : '',
                            old_price_text: oldPriceEl ? oldPriceEl.textContent.trim() : '',
                            image: imageEl ? imageEl.src : '',
                            rating_text: ratingEl ? ratingEl.textContent.trim() : '',
                            has_prime: hasPrime,
                            has_discount_tag: hasDiscount,
                        };
                    });
                }
            """)

            seen_titles = set()
            results = []
            for item in items:
                try:
                    title = item["title"]
                    if not title or len(title) < 5:
                        continue
                    if title in seen_titles:
                        continue
                    price = self._parse_brl(item["price_text"])
                    if price <= 0:
                        continue
                    old_price = self._parse_brl(item["old_price_text"])
                    has_discount = old_price > 0 and price < old_price * 0.99
                    promo = has_discount or item["has_discount_tag"]
                    ship_free = item["has_prime"]
                    rating_match = re.search(r"([\d,]+)", item["rating_text"])
                    if promotion and not promo:
                        continue
                    if free_shipping and not ship_free:
                        continue
                    if max_price and price > max_price:
                        continue
                    seen_titles.add(title)
                    u = item["url"]
                    if u and u.startswith("/"):
                        u = "https://www.amazon.com.br" + u
                    results.append({
                        "title": title,
                        "url": u,
                        "price": price,
                        "old_price": old_price if old_price > 0 else None,
                        "discount": "",
                        "has_discount": has_discount,
                        "promotion_tag": promo,
                        "free_shipping": ship_free,
                        "installments": "",
                        "rating": rating_match.group(1) if rating_match else "",
                        "reviews": "",
                        "store": "Amazon Brasil",
                        "image": item["image"],
                        "source": "amazon",
                    })
                except Exception as e:
                    logger.warning(f"Parse Amazon item error: {e}")
                    continue
            return results
        except Exception as e:
            logger.error(f"Amazon search error: {e}")
            return []
        finally:
            if context:
                await context.close()

    def _parse_brl(self, text: str) -> float:
        if not text:
            return 0.0
        text = text.strip().replace("R$", "").replace(" ", "")
        if "," in text:
            text = text.replace(".", "")
            text = text.replace(",", ".")
        text = re.sub(r'[^\d.]', '', text)
        try:
            return float(text) if text else 0.0
        except ValueError:
            return 0.0


manifest = PluginManifest(
    name="shopping",
    version="1.0.0",
    description="Shopping - search products with free shipping and promotions on Mercado Livre, Magazine Luiza, Amazon Brasil",
    tags=["shopping", "ecommerce", "products", "brazil"],
)
