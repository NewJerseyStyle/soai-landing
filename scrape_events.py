import json
import hashlib
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "data/events.json"

AI_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "machine learning",
    "genai",
    "llm",
    "deep learning",
]


def is_ai_event(title):
    t = (title or "").lower()
    return any(k in t for k in AI_KEYWORDS)


def make_id(source, title, key):
    raw = f"{source}-{title}-{key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9",
    "Referer": "https://www.google.com/",
})


def safe_request(url):
    """Return Response on success, None on failure (incl. bot-block 403/429)."""
    try:
        r = session.get(url, timeout=20)
        time.sleep(2)
        if r.status_code in (401, 403, 429):
            print(f"[SKIP] {url} -> {r.status_code} (site blocks automated access)")
            return None
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return None


# ----------------------------
# HKSTP — public JSON API, robots.txt does not disallow it
# ----------------------------

def scrape_hkstp():
    events = []
    url = (
        "https://www.hkstp.org/api/List/NewsEventSearch"
        "?page=1&pageSize=50"
        "&category=all&year=all&month=all&alphabet=all"
        "&language=en&site=website&database=web"
        "&source=0853B80DF96741F18D986A7F4530E13B"
        "&renderingsource=6C236FB3570F431993AE3994466ACB35"
        "&tabheadersource=5272A2BE217C4D89B2FE0A60AF5A25A9"
        "&tabstyle=style1"
    )

    r = safe_request(url)
    if r is None:
        return events
    try:
        data = r.json()
    except ValueError as e:
        print(f"[ERROR] HKSTP JSON parse: {e}")
        return events

    items = data.get("results") or data.get("Results") or data.get("items") or []
    for item in items:
        title = item.get("title") or item.get("Title")
        link = item.get("url") or item.get("Url")
        date = item.get("date") or item.get("Date")
        if not title or not link:
            continue
        if link.startswith("/"):
            link = "https://www.hkstp.org" + link
        if not is_ai_event(title):
            # HKSTP feed mixes all corporate news; keep only AI-relevant items
            continue
        events.append({
            "id": make_id("HKSTP", title, link),
            "title": title.strip(),
            "start_time": date,
            "location": "Hong Kong Science Park",
            "source": "HKSTP",
            "url": link,
            "tags": ["AI"],
        })
    return events


# ----------------------------
# Cyberport — SKIPPED
# Cloudflare challenge returns 403 to non-browser clients. Treat as
# "do not crawl" until/unless they publish a feed or grant access.
# ----------------------------

def scrape_cyberport():
    print("[SKIP] Cyberport: site is behind Cloudflare bot protection")
    return []


# ----------------------------
# HKPC — SKIPPED
# Imperva/Incapsula challenge returns 403 to non-browser clients.
# ----------------------------

def scrape_hkpc():
    print("[SKIP] HKPC: site is behind Imperva bot protection")
    return []


# ----------------------------
# AI Tinkerers — Hong Kong chapter
# ----------------------------

def scrape_ai_tinkerers():
    events = []
    base = "https://hong-kong.aitinkerers.org"
    r = safe_request(base + "/")
    if r is None:
        return events

    soup = BeautifulSoup(r.text, "html.parser")

    # Each upcoming meetup is rendered as an <a href=".../talks/rsvp_XXXX">
    seen = set()
    for a in soup.select("a[href*='/talks/rsvp_']"):
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)

        if href.startswith("/"):
            href = base + href

        # Title: prefer a heading inside the card, else first non-empty text line
        title = None
        heading = a.find(["h1", "h2", "h3", "h4"])
        if heading:
            title = heading.get_text(" ", strip=True)
        if not title:
            text = a.get_text("\n", strip=True)
            for line in text.splitlines():
                line = line.strip()
                if line and not line.lower().startswith(("rsvp", "next:")):
                    title = line
                    break
        if not title:
            title = "AI Tinkerers Hong Kong meetup"

        # Date: look for an explicit datetime attribute inside the card
        date_str = None
        time_tag = a.find("time")
        if time_tag:
            date_str = time_tag.get("datetime") or time_tag.get_text(strip=True)

        events.append({
            "id": make_id("AI Tinkerers", title, href),
            "title": title,
            "start_time": date_str,
            "location": "Hong Kong",
            "source": "AI Tinkerers",
            "url": href,
            "tags": ["AI"],
        })

    return events


# ----------------------------
# Main
# ----------------------------

def main():
    all_events = []

    sources = [
        scrape_hkstp,
        scrape_cyberport,
        scrape_hkpc,
        scrape_ai_tinkerers,
    ]

    for source_func in sources:
        print(f"Running {source_func.__name__}...")
        try:
            all_events.extend(source_func())
        except Exception as e:
            print(f"[ERROR] {source_func.__name__} failed: {e}")

    unique = {}
    for e in all_events:
        unique[e["id"]] = e
    all_events = list(unique.values())

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "events": all_events,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_events)} events to {OUTPUT_FILE}.")


if __name__ == "__main__":
    main()
