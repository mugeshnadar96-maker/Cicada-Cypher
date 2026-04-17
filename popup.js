// popup.js — Handles UI interactions, messaging, and API communication

const API_ENDPOINT = "http://localhost:8000/analyze";

// ── DOM references ────────────────────────────────────────────────────────────
const analyzeBtn   = document.getElementById("analyzeBtn");
const statusEl     = document.getElementById("status");
const resultsEl    = document.getElementById("results");
const productMeta  = document.getElementById("productMeta");

// Result field elements
const fieldUserPrice  = document.getElementById("field-user_price");
const fieldBestPrice  = document.getElementById("field-best_price");
const fieldLabel      = document.getElementById("field-label");
const fieldReason     = document.getElementById("field-reason");
const fieldSuggestion = document.getElementById("field-suggestion");

// ── Helpers ───────────────────────────────────────────────────────────────────

function setStatus(message, type = "info") {
  statusEl.textContent = message;
  statusEl.className = `status status--${type}`;
  statusEl.hidden = false;
}

function clearStatus() {
  statusEl.hidden = true;
  statusEl.textContent = "";
}

function showResults(apiResponse) {
  // Populate each field
  fieldUserPrice.textContent  = apiResponse.user_price  ?? "—";
  fieldBestPrice.textContent  = apiResponse.best_price  ?? "—";
  fieldLabel.textContent      = apiResponse.label       ?? "—";
  fieldReason.textContent     = apiResponse.reason      ?? "—";
  fieldSuggestion.textContent = apiResponse.suggestion  ?? "—";

  // Color-code the label badge
  const labelEl = document.getElementById("field-label");
  labelEl.className = "value"; // reset
  const labelLower = (apiResponse.label ?? "").toLowerCase();
  if (labelLower.includes("good") || labelLower.includes("fair")) {
    labelEl.classList.add("value--good");
  } else if (labelLower.includes("high") || labelLower.includes("overpriced")) {
    labelEl.classList.add("value--bad");
  } else {
    labelEl.classList.add("value--neutral");
  }

  resultsEl.hidden = false;
  resultsEl.classList.add("results--visible");
}

function setLoading(isLoading) {
  analyzeBtn.disabled = isLoading;
  analyzeBtn.textContent = isLoading ? "Analyzing…" : "Analyze Price";
  if (isLoading) analyzeBtn.classList.add("btn--loading");
  else analyzeBtn.classList.remove("btn--loading");
}

// ── Core flow ─────────────────────────────────────────────────────────────────

async function fetchActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("No active tab found.");
  return tab;
}

async function extractProductData(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, { action: "getProductData" }, (response) => {
      if (chrome.runtime.lastError) {
        return reject(new Error(chrome.runtime.lastError.message));
      }
      if (!response?.success) {
        return reject(new Error("Content script did not return valid data."));
      }
      resolve(response.data);
    });
  });
}

async function postToApi(productData) {
  const response = await fetch(API_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(productData),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// ── Main handler ──────────────────────────────────────────────────────────────

analyzeBtn.addEventListener("click", async () => {
  resultsEl.hidden = true;
  clearStatus();
  setLoading(true);

  try {
    // Step 1: Get active tab
    const tab = await fetchActiveTabId();

    // Step 2: Extract product data via content script
    setStatus("Extracting product details…", "info");
    let productData;
    try {
      productData = await extractProductData(tab.id);
    } catch {
      // Content script may not be injected yet — inject it manually
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"],
      });
      productData = await extractProductData(tab.id);
    }

    if (!productData.title && !productData.price) {
      throw new Error("Could not detect a product on this page.");
    }

    // Show what was extracted
    productMeta.textContent = `📦 ${productData.title || "Unknown product"} · ${productData.price || "Price not found"}`;
    productMeta.hidden = false;

    // Step 3: Send to backend API
    setStatus("Sending to API…", "info");
    const apiResponse = await postToApi(productData);

    // Step 4: Display results
    clearStatus();
    showResults(apiResponse);

  } catch (err) {
    setStatus(`Error: ${err.message}`, "error");
    console.error("[PriceAnalyzer]", err);
  } finally {
    setLoading(false);
  }
});
