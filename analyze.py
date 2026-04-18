import asyncio
import re
import time
from playwright.async_api import async_playwright, Page, Browser

# ---------------- CONFIG ----------------
LOCATIONS = {
    "delhi": "110001",
    "mumbai": "400001",
    "bangalore": "560001",
}

PRICE_SELECTORS = [
    ".a-price-whole",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "span[class*='price']",
]

# ---------------- HELPERS ----------------
def clean_price(text):
    if not text:
        return None
    nums = re.findall(r"\d+", text.replace(",", ""))
    return int("".join(nums)) if nums else None


async def block_resources(route):
    if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
        await route.abort()
    else:
        await route.continue_()


async def fast_goto(page: Page, url: str):
    await page.route("**/*", block_resources)
    await page.goto(url, wait_until="commit", timeout=30000)


async def simulate_behavior(page: Page):
    await page.mouse.move(200, 300)
    await page.mouse.wheel(0, 800)
    await page.wait_for_timeout(800)


async def open_via_search(page: Page, product_url: str):
    try:
        await page.goto("https://www.amazon.in", wait_until="commit")
        await page.fill("#twotabsearchtextbox", "product")
        await page.press("#twotabsearchtextbox", "Enter")
        await page.wait_for_timeout(800)
        await page.locator("a[href*='/dp/']").first.click()
        await page.wait_for_timeout(800)
    except:
        await page.goto(product_url)


async def extract_price(page: Page):
    for selector in PRICE_SELECTORS:
        try:
            element = page.locator(selector).first
            text = await element.text_content()
            price = clean_price(text)
            if price:
                return price
        except:
            continue
    return None


# ---------------- FETCH ----------------
async def fetch_incognito(browser: Browser, url: str):
    context = await browser.new_context()
    page = await context.new_page()

    await open_via_search(page, url)
    await simulate_behavior(page)

    price = await extract_price(page)
    await context.close()
    return price


async def fetch_mobile(browser: Browser, url: str):
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        viewport={"width": 375, "height": 812},
        is_mobile=True,
    )

    page = await context.new_page()
    await fast_goto(page, url)
    price = await extract_price(page)

    await context.close()
    return price


async def fetch_location(browser: Browser, url: str, pincode: str):
    context = await browser.new_context()
    page = await context.new_page()

    await fast_goto(page, url)
    price = await extract_price(page)

    await context.close()
    return price


async def fetch_prices(url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        part1 = await asyncio.gather(
            fetch_incognito(browser, url),
            fetch_mobile(browser, url),
        )

        part2 = await asyncio.gather(
            fetch_location(browser, url, LOCATIONS["delhi"]),
            fetch_location(browser, url, LOCATIONS["mumbai"]),
            fetch_location(browser, url, LOCATIONS["bangalore"]),
        )

        await browser.close()

    return {
        "incognito": part1[0],
        "mobile": part1[1],
        "delhi": part2[0],
        "mumbai": part2[1],
        "bangalore": part2[2],
    }


# ---------------- ANALYSIS ----------------
def normalize(value):
    return value if isinstance(value, (int, float)) else "NA"


def get_valid_prices(result):
    return {k: v for k, v in result.items() if isinstance(v, (int, float))}


def get_best_price(valid_prices):
    return min(valid_prices.values()) if valid_prices else "NA"


def calculate_deviation(user_price, best_price):
    if user_price == "NA" or best_price == "NA" or best_price == 0:
        return "NA"
    return round(((user_price - best_price) / best_price) * 100, 2)


def classify(deviation):
    if deviation == "NA":
        return "NA"
    if deviation < 5:
        return "Fair"
    elif deviation <= 15:
        return "Slightly Inflated"
    else:
        return "Highly Manipulated"


def generate_reason(user_price, result):
    if user_price == "NA":
        return "User price unavailable."

    if result.get("incognito") and user_price > result["incognito"]:
        return "Higher price due to tracking-based pricing."

    if result.get("mobile") and user_price > result["mobile"]:
        return "Higher price due to device-based pricing."

    if result.get("delhi") and user_price > result["delhi"]:
        return "Price varies based on location."

    return "No strong pricing bias detected."


def generate_suggestion(valid_prices):
    if not valid_prices:
        return "No suggestion available."

    best = min(valid_prices, key=valid_prices.get)

    suggestions = {
        "incognito": "Use incognito mode.",
        "mobile": "Switch to mobile.",
        "delhi": "Try Delhi location.",
        "mumbai": "Try Mumbai location.",
        "bangalore": "Try Bangalore location.",
    }

    return suggestions.get(best, "Compare environments.")


def analyze_fetch_output(fetch_result):
    normalized = {k: normalize(v) for k, v in fetch_result.items()}
    valid_prices = get_valid_prices(fetch_result)

    user_price = normalize(fetch_result.get("incognito"))
    best_price = get_best_price(valid_prices)

    deviation = calculate_deviation(user_price, best_price)
    label = classify(deviation)
    reason = generate_reason(user_price, fetch_result)
    suggestion = generate_suggestion(valid_prices)

    return {
        "user_price": user_price,
        "best_price": best_price,
        "deviation": deviation,
        "label": label,
        "breakdown": normalized,
        "reason": reason,
        "suggestion": suggestion,
    }


# ---------------- MAIN ----------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py <product_url>")
        exit()

    url = sys.argv[1]

    start = time.time()

    fetched = asyncio.run(fetch_prices(url))
    analysis = analyze_fetch_output(fetched)

    print("\n--- FETCHED DATA ---")
    print(fetched)

    print("\n--- ANALYSIS ---")
    print(analysis)

    print(f"\n⏱ Time: {round(time.time() - start, 2)}s")