"""
Image Search API — FastAPI + Playwright + Chromium
===================================================
Optimised for Render free tier (512 MB RAM):
  - No persistent browser process — launches & kills per request
  - Minimal Chromium flags to keep memory low
  - Reduced scroll steps & smaller viewport

Install:
    pip install fastapi uvicorn playwright
    playwright install chromium

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import re
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright


# ── Config ─────────────────────────────────────────────────────────────────────
SCROLL_STEPS    = 2          # fewer scrolls = less memory pressure
SCROLL_PAUSE_MS = 800
TIMEOUT_MS      = 25_000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",        # critical: avoids /dev/shm OOM
    "--disable-gpu",
    "--no-zygote",
    "--single-process",               # biggest RAM saving
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--hide-scrollbars",
    "--mute-audio",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
]


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Image Search API",
    description="Automated Google Image search using Playwright + Chromium.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────
class ImageResult(BaseModel):
    index:      int
    title:      str
    src:        str
    page_url:   str
    dimensions: str


class SearchResponse(BaseModel):
    query:      str
    fetched_at: str
    total:      int
    images:     list[ImageResult]


# ── Helpers ────────────────────────────────────────────────────────────────────
def sanitize(text: str, max_len: int = 300) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:max_len]


# ── Scraper — fresh browser per request ───────────────────────────────────────
async def run_scraper(query: str, max_results: int) -> list[ImageResult]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=CHROMIUM_ARGS,
        )
        try:
            page = await browser.new_page(
                viewport={"width": 1280, "height": 800},
                user_agent=USER_AGENT,
                locale="en-US",
            )
            page.set_default_timeout(TIMEOUT_MS)

            url = (
                "https://www.google.com/search"
                f"?tbm=isch&q={query.replace(' ', '+')}&safe=active"
            )
            await page.goto(url, wait_until="domcontentloaded")

            # Accept EU consent if shown
            try:
                btn = page.locator('button:has-text("Accept all")')
                if await btn.is_visible(timeout=2_000):
                    await btn.click()
                    await page.wait_for_timeout(600)
            except Exception:
                pass

            # Scroll to load images
            for _ in range(SCROLL_STEPS):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
                await page.wait_for_timeout(SCROLL_PAUSE_MS)

            # Extract image metadata
            raw: list[dict] = await page.evaluate("""() => {
                const results = [];

                document.querySelectorAll("div[data-attrid], div[jsname]").forEach(el => {
                    const img = el.querySelector("img[src]");
                    if (!img || !img.src.startsWith("http")) return;
                    results.push({
                        src: img.src,
                        title: el.querySelector("[aria-label]")?.getAttribute("aria-label")
                            || el.querySelector("a")?.getAttribute("aria-label")
                            || img.alt || "",
                        page_url: el.querySelector("a[href]")?.href || "",
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                    });
                });

                if (results.length < 5) {
                    document.querySelectorAll("img[src]").forEach(img => {
                        if (img.src.startsWith("http") && img.naturalWidth > 50 && img.naturalHeight > 50) {
                            results.push({
                                src: img.src,
                                title: img.alt || "",
                                page_url: img.closest("a")?.href || "",
                                width: img.naturalWidth,
                                height: img.naturalHeight,
                            });
                        }
                    });
                }

                return results;
            }""")

        finally:
            await browser.close()   # always free memory immediately

    # Deduplicate & limit
    seen: set[str] = set()
    images: list[ImageResult] = []
    for item in raw:
        if item["src"] in seen:
            continue
        seen.add(item["src"])
        w, h = item.get("width", 0), item.get("height", 0)
        images.append(ImageResult(
            index=len(images) + 1,
            title=sanitize(item.get("title", "")),
            src=item["src"],
            page_url=item.get("page_url", ""),
            dimensions=f"{w}×{h}" if w and h else "unknown",
        ))
        if len(images) >= max_results:
            break

    return images


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "Image Search API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "search": "GET /search?q=<query>&count=<n>",
            "health": "GET /health",
        },
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/search", response_model=SearchResponse)
async def search_images(
    q:     str = Query(..., min_length=1, max_length=200, description="Search query"),
    count: int = Query(default=10, ge=1, le=50, description="Number of images (1–50)"),
):
    """
    Search Google Images and return structured results.

    - **q**: search term (required)
    - **count**: how many images to return (default 10, max 50)
    """
    try:
        images = await run_scraper(q, count)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not images:
        raise HTTPException(status_code=404, detail=f"No images found for: {q!r}")

    return SearchResponse(
        query=q,
        fetched_at=datetime.utcnow().isoformat() + "Z",
        total=len(images),
        images=images,
    )
