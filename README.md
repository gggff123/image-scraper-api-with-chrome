# image-scraper-api-with-chrome
# 🔍 Image Search API

A fast, automated image search API built with **FastAPI** and **Playwright (Chromium)**. Send a query, get back structured image results scraped from Google Images — no API key required.

---

## ✨ Features

- 🤖 Headless Chromium automation via Playwright
- ⚡ Async FastAPI with a single shared browser instance
- 🔄 Auto-scrolling to load more results
- 🧹 Deduplication & clean JSON responses
- 📖 Auto-generated Swagger UI at `/docs`
- 🌍 CORS enabled for frontend integration

---

## 📦 Requirements

- Python 3.10+
- pip

---

## 🚀 Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/gggff123/image-scraper-api-with-chrome
.git
cd image-scraper-api-with-chrome

```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Run the server

```bash
uvicorn main:app --reload --port 8000
```

Server is live at **http://localhost:8000**

---

## 📡 API Endpoints

### `GET /`
Returns service info and available endpoints.

### `GET /health`
Check if the server and browser are running.

```json
{
  "status": "ok",
  "browser": "running",
  "timestamp": "2026-03-04T10:00:00Z"
}
```

### `GET /search`

Search for images by query.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | ✅ | — | Search query |
| `count` | integer | ❌ | `20` | Number of results (max 100) |

**Example request:**
```bash
curl "http://localhost:8000/search?q=sunset+ocean&count=10"
```

**Example response:**
```json
{
  "query": "sunset ocean",
  "fetched_at": "2026-03-04T10:00:00Z",
  "total": 10,
  "images": [
    {
      "index": 1,
      "title": "Beautiful sunset over the ocean",
      "src": "https://example.com/image.jpg",
      "page_url": "https://example.com/page",
      "dimensions": "1280×720"
    }
  ]
}
```

---

## 📖 Interactive Docs

Once running, visit:

- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc

---
##Works on 
- **Linux**
- **Windows**
## ⚠️ Notes

- This project scrapes Google Images. Use responsibly and respect [Google's Terms of Service](https://policies.google.com/terms).
- Intended for personal/educational use.
- Heavy usage may result in temporary IP blocks from Google.

---

## 📄 License

MIT — free to use, modify, and distribute.
