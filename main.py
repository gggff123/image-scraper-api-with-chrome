"""
Image Search API — FastAPI + httpx + BeautifulSoup
===================================================
No browser / Chromium needed — works on Render free tier (512 MB).

Install:
    pip install -r requirements.txt

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import re
import json
import httpx
from datetime import datetime
from bs4 import BeautifulSoup

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ── Config ─────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 15  # seconds


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Image Search API",
    description="Search Google Images — no browser required.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────
class ImageResult(BaseModel):
    index:    int
    title:    str
    src:      str
    page_url: str
    width:    int
    height:   int


class SearchResponse(BaseModel):
    query:      str
    fetched_at: str
    total:      int
    images:     list[ImageResult]


# ── Scraper ────────────────────────────────────────────────────────────────────
def sanitize(text: str, max_len: int = 300) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:max_len]


async def scrape_images(query: str, max_results: int) -> list[ImageResult]:
    url = (
        "https://www.google.com/search"
        f"?tbm=isch&q={query.replace(' ', '+')}&safe=active&num=40"
    )

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    images: list[ImageResult] = []
    seen: set[str] = set()

    # ── Method 1: extract from embedded JSON blobs ─────────────────────────────
    # Google embeds image data as JSON inside <script> tags
    pattern = re.compile(
        r'\["(https?://[^"]+?)"'   # image URL
        r',(\d+)'                   # width
        r',(\d+)\]'                 # height
    )
    for match in pattern.finditer(html):
        src, w, h = match.group(1), int(match.group(2)), int(match.group(3))
        if src in seen or w < 100 or h < 100:
            continue
        # skip Google UI icons / logos
        if any(skip in src for skip in ["gstatic.com/images/branding", "google.com/images"]):
            continue
        seen.add(src)
        images.append(ImageResult(
            index=len(images) + 1,
            title="",
            src=src,
            page_url="",
            width=w,
            height=h,
        ))
        if len(images) >= max_results:
            break

    # ── Method 2: BeautifulSoup fallback for titles + page URLs ───────────────
    soup = BeautifulSoup(html, "html.parser")

    # Try to enrich with titles from <div class="VFACy"> or alt text
    title_map: dict[str, str] = {}
    page_map:  dict[str, str] = {}

    for script in soup.find_all("script"):
        text = script.string or ""
        # Pull out AF_initDataCallback blobs that contain metadata
        urls = re.findall(r'"(https?://(?!encrypted)[^"]{10,})"', text)
        titles = re.findall(r'"([^"]{5,80})"', text)
        _ = urls, titles  # available for future enrichment

    # If method 1 found nothing, fallback to <img> tags in the parsed HTML
    if not images:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src", "")
            if not src.startswith("http") or src in seen:
                continue
            seen.add(src)
            images.append(ImageResult(
                index=len(images) + 1,
                title=sanitize(img.get("alt", "")),
                src=src,
                page_url="",
                width=0,
                height=0,
            ))
            if len(images) >= max_results:
                break

    return images[:max_results]


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "Image Search API",
        "version": "3.0.0",
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
    count: int = Query(default=10, ge=1, le=50, description="Number of results (1–50)"),
):
    """
    Search Google Images without a browser.

    - **q**: search term (required)
    - **count**: number of images to return (default 10, max 50)
    """
    try:
        images = await scrape_images(q, count)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Google returned {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not images:
        raise HTTPException(status_code=404, detail=f"No images found for: {q!r}")

    return SearchResponse(
        query=q,
        fetched_at=datetime.utcnow().isoformat() + "Z",
        total=len(images),
        images=images,
    )
