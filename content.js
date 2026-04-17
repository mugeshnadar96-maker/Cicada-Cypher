// content.js — Extracts product data from the active e-commerce page

/**
 * Extracts the product title from the first <h1> on the page.
 * @returns {string} Trimmed title text, or empty string if not found.
 */
function extractTitle() {
  const h1 = document.querySelector("h1");
  return h1 ? h1.innerText.trim() : "";
}

/**
 * Extracts the first price found in ₹ (Indian Rupee) format.
 * Handles formats like: ₹1,499 / ₹1499 / ₹ 1,499.00
 * @returns {string} Raw matched price string, or empty string if not found.
 */
function extractPrice() {
  // Walk all visible text nodes to find a ₹ price pattern
  const priceRegex = /₹\s?[\d,]+(\.\d{1,2})?/;

  // Prefer meta tag (most reliable on structured pages)
  const metaPrice = document.querySelector(
    'meta[property="product:price:amount"], meta[itemprop="price"]'
  );
  if (metaPrice) {
    const val = metaPrice.getAttribute("content");
    if (val) return `₹${parseFloat(val).toLocaleString("en-IN")}`;
  }

  // Try common price selector classes used by major e-commerce sites
  const priceSelectors = [
    '[class*="price"]',
    '[id*="price"]',
    '[class*="Price"]',
    '[data-testid*="price"]',
    ".a-price .a-offscreen", // Amazon
    ".pdp-price",            // Flipkart-style
    ".product-price",
  ];

  for (const selector of priceSelectors) {
    const el = document.querySelector(selector);
    if (el) {
      const text = el.innerText || el.textContent || "";
      const match = text.match(priceRegex);
      if (match) return match[0].replace(/\s/, "");
    }
  }

  // Fallback: scan entire body text
  const bodyText = document.body.innerText || "";
  const match = bodyText.match(priceRegex);
  return match ? match[0].replace(/\s/, "") : "";
}

/**
 * Builds and returns the product data object.
 * @returns {{ title: string, price: string, url: string }}
 */
function getProductData() {
  return {
    title: extractTitle(),
    price: extractPrice(),
    url: window.location.href,
  };
}

// Listen for messages from popup.js
chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === "getProductData") {
    const data = getProductData();
    sendResponse({ success: true, data });
  }
  // Return true to keep the message channel open for async if needed
  return true;
});
