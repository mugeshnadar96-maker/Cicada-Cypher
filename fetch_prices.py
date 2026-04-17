"""
fetch_prices.py
---------------
Async Playwright script to fetch product prices from an e-commerce URL
under three conditions: incognito, mobile, and Delhi (pincode 110001).

Usage:
    pip install playwright
    playwright install chromium
    python fetch_prices.py <URL>
"""

import asyncio
import re
import sys
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext


# ---------------------------------------------------------------------------
# Price selectors — ordered by specificity; first match wins
# ---------------------------------------------------------------------------
PRICE_SELECTORS = [
    # Amazon
    "span.a-price-whole",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#corePriceDisplay_desktop_feature_div span.a-price-whole",
    # Flipkart
    "div._30jeq3._16Jk6d",
    "div._30jeq3",
    # Myntra / Ajio / generic
    "span.pdp-price strong",
    "span[class*='price']",
    "div[class*='price'] span",
    "p[class*='price']",
    # Schema / meta fallback
    "[itemprop='price']",
    "[data-price]",
]

MOBILE_DEVICE = {
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Mobile Safari/537.36"
    ),
    "viewport": {"width": 390, "height": 844},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}

DELHI_PINCODE = "110001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_price(raw: str) -> Optional[int]:
    """Strip currency symbols / commas and return an integer price."""
    digits = re.sub(r"[^\d]", "", raw.split(".")[0])  # keep only digits, drop decimals
    return int(digits) if digits else None


async def extract_price(page: Page) -> Optional[int]:
    """Try each selector in order; return the first numeric price found."""
    for selector in PRICE_SELECTORS:
        try:
            locator = page.locator(selector).first
            # wait briefly — don't block the whole run on a missing element
            await locator.wait_for(state="visible", timeout=4_000)
            text = await locator.inner_text()
            price = clean_price(text)
            if price and price > 0:
                return price
        except Exception:
            continue

    # Last resort: search full page text for ₹ pattern
    try:
        body = await page.inner_text("body")
        matches = re.findall(r"₹\s*([\d,]+)", body)
        for m in matches:
            price = clean_price(m)
            if price and price > 0:
                return price
    except Exception:
        pass

    return None


async def navigate(page: Page, url: str, timeout: int = 30_000) -> None:
    """Navigate and wait until network is mostly idle."""
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass  # networkidle can time-out on heavy pages; that's fine


# ---------------------------------------------------------------------------
# Condition-specific fetchers
# ---------------------------------------------------------------------------

async def fetch_incognito(browser, url: str) -> Optional[int]:
    """Fresh incognito context — no cookies, no cache."""
    context: BrowserContext = await browser.new_context(
        java_script_enabled=True,
    )
    try:
        page = await context.new_page()
        await navigate(page, url)
        return await extract_price(page)
    except Exception as exc:
        print(f"[incognito] Error: {exc}", file=sys.stderr)
        return None
    finally:
        await context.close()


async def fetch_mobile(browser, url: str) -> Optional[int]:
    """Mobile viewport + mobile user-agent."""
    context: BrowserContext = await browser.new_context(
        user_agent=MOBILE_DEVICE["user_agent"],
        viewport=MOBILE_DEVICE["viewport"],
        device_scale_factor=MOBILE_DEVICE["device_scale_factor"],
        is_mobile=MOBILE_DEVICE["is_mobile"],
        has_touch=MOBILE_DEVICE["has_touch"],
        java_script_enabled=True,
    )
    try:
        page = await context.new_page()
        await navigate(page, url)
        return await extract_price(page)
    except Exception as exc:
        print(f"[mobile] Error: {exc}", file=sys.stderr)
        return None
    finally:
        await context.close()


async def _set_delhi_pincode(page: Page) -> None:
    """
    Attempt to change the delivery location to Delhi (110001).
    Covers common patterns used by Amazon, Flipkart, and generic sites.
    """

    # ---- Pattern 1: Amazon-style "Deliver to" link ----
    try:
        deliver_btn = page.locator(
            "#nav-global-location-popover-link, [data-action='nav-location']"
        ).first
        await deliver_btn.wait_for(state="visible", timeout=3_000)
        await deliver_btn.click()
        pincode_input = page.locator(
            "input[placeholder*='pincode'], input[placeholder*='PIN'], "
            "input#GLUXZipUpdateInput, input[name='GLUXZipUpdateInput']"
        ).first
        await pincode_input.wait_for(state="visible", timeout=4_000)
        await pincode_input.fill(DELHI_PINCODE)
        apply_btn = page.locator(
            "input[aria-labelledby*='GLUXZipUpdate'], "
            "span#GLUXZipUpdate input, "
            "button[aria-label*='Apply']"
        ).first
        await apply_btn.click(timeout=4_000)
        await page.wait_for_timeout(2_000)
        return
    except Exception:
        pass

    # ---- Pattern 2: Flipkart-style pincode checker ----
    try:
        pin_input = page.locator(
            "input[placeholder*='Enter Delivery Pincode'], "
            "input[placeholder*='pincode']"
        ).first
        await pin_input.wait_for(state="visible", timeout=3_000)
        await pin_input.fill(DELHI_PINCODE)
        check_btn = page.locator(
            "button:has-text('Check'), button:has-text('Apply')"
        ).first
        await check_btn.click(timeout=3_000)
        await page.wait_for_timeout(2_000)
        return
    except Exception:
        pass

    # ---- Pattern 3: Generic modal / overlay with pincode field ----
    try:
        triggers = page.locator(
            "button:has-text('Change'), a:has-text('Change'), "
            "[class*='location'], [class*='pincode']"
        )
        if await triggers.count() > 0:
            await triggers.first.click(timeout=3_000)
            await page.wait_for_timeout(1_000)
            generic_input = page.locator(
                "input[type='text'][maxlength='6'], "
                "input[inputmode='numeric'][maxlength='6']"
            ).first
            await generic_input.fill(DELHI_PINCODE)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2_000)
    except Exception:
        pass  # Location could not be set — price will still be extracted


async def fetch_delhi(browser, url: str) -> Optional[int]:
    """Set delivery location to Delhi then extract price."""
    context: BrowserContext = await browser.new_context(java_script_enabled=True)
    try:
        page = await context.new_page()
        await navigate(page, url)
        await _set_delhi_pincode(page)
        # Re-extract after potential page reload triggered by location change
        try:
            await page.wait_for_load_state("networkidle", timeout=6_000)
        except Exception:
            pass
        return await extract_price(page)
    except Exception as exc:
        print(f"[delhi] Error: {exc}", file=sys.stderr)
        return None
    finally:
        await context.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_prices(url: str) -> dict:
    """
    Fetch product price from *url* under three conditions.

    Returns:
        {
            "incognito": <int or None>,
            "mobile":    <int or None>,
            "delhi":     <int or None>,
        }
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            incognito_price, mobile_price, delhi_price = await asyncio.gather(
                fetch_incognito(browser, url),
                fetch_mobile(browser, url),
                fetch_delhi(browser, url),
            )
        finally:
            await browser.close()

    return {
        "incognito": incognito_price,
        "mobile": mobile_price,
        "delhi": delhi_price,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_prices.py <product-url>")
        sys.exit(1)

    target_url = sys.argv[1]
    result = asyncio.run(fetch_prices(target_url))
    print(result)
