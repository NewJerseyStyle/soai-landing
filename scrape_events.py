import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import hashlib
import time

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
    t = title.lower()
    return any(k in t for k in AI_KEYWORDS)

# ----------------------------
# Utility
# ----------------------------

def make_id(source, title, date_str):
    raw = f"{source}-{title}-{date_str}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def normalize_event(source, title, date_str, url, location):
    return {
        "id": make_id(source, title, date_str),
        "title": title.strip(),
        "start_time": date_str,
        "location": location,
        "source": source,
        "url": url.strip(),
        "tags": ["AI"]
    }


session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://www.google.com/"
})

def safe_request(url):
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        time.sleep(2)
        return r.text
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")
        return None


# ----------------------------
# HKSTP
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

    try:
        r = safe_request(url)
        data = r.json()
    except Exception as e:
        print("HKSTP API error:", e)
        return events

    # JSON structure usually:
    # data["items"] or data["Results"]
    items = data.get("Results") or data.get("items") or []

    for item in items:
        title = item.get("Title") or item.get("title")
        link = item.get("Url") or item.get("url")
        date = item.get("Date") or item.get("date")

        if not title or not link:
            continue

        if link.startswith("/"):
            link = "https://www.hkstp.org" + link

        events.append({
            "id": make_id("HKSTP", title, link),
            "title": title,
            "start_time": date,
            "location": "Hong Kong Science Park",
            "source": "HKSTP",
            "url": link,
            "tags": ["AI"]
        })

    return events

# ----------------------------
# Cyberport
# ----------------------------

def scrape_cyberport():
    events = []

    url = "https://www.cyberport.hk/en/news/events/"
    html = safe_request(url)
    if not html:
        return events

    soup = BeautifulSoup(html, "html.parser")

    cards = soup.select("li.flex.flex-col")

    for card in cards:

        title_tag = card.select_one("h3 a")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get("href")

        status = card.select_one("span.event-status")

        start_date = None
        if status:
            start_date = status.get("data-startdate")

        if not title or not link:
            continue

        events.append({
            "id": make_id("Cyberport", title, link),
            "title": title,
            "start_time": start_date,
            "location": "Cyberport",
            "source": "Cyberport",
            "url": link,
            "tags": ["AI"]
        })

    return events

# ----------------------------
# HKPC
# ----------------------------

def scrape_hkpc():
    events = []

    url = "https://www.hkpc.org/en/hkpc-spotlights/events/corporate-events"
    html = safe_request(url)
    if not html:
        return events

    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.table-style")
    if not table:
        return events

    rows = table.select("tbody tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        date_text = cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True)

        link_tag = cols[2].find("a")
        if not link_tag:
            continue

        url = link_tag.get("href")

        events.append({
            "id": make_id("HKPC", title, url),
            "title": title,
            "start_time": date_text,
            "location": "HKPC",
            "source": "HKPC",
            "url": url,
            "tags": ["AI"]
        })

    return events


# ----------------------------
# AI Tinkerers (if HK chapter page exists)
# ----------------------------

def scrape_ai_tinkerers():
    events = []

    url = "https://aitinkerers.org"
    html = safe_request(url)
    if not html:
        return events

    soup = BeautifulSoup(html, "html.parser")

    for link in soup.select("a[href*='hong-kong']"):
        title = link.get_text(strip=True)
        href = link.get("href")

        if not title:
            title = "AI Tinkerers Hong Kong"

        if href.startswith("/"):
            href = "https://aitinkerers.org" + href

        events.append({
            "id": make_id("AI Tinkerers", title, href),
            "title": title,
            "start_time": None,
            "location": "Hong Kong",
            "source": "AI Tinkerers",
            "url": href,
            "tags": ["AI"]
        })

        break  # only one HK chapter

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
        scrape_ai_tinkerers
    ]

    for source_func in sources:
        try:
            print(f"Running {source_func.__name__}...")
            all_events.extend(source_func())
        except Exception as e:
            print(f"[ERROR] {source_func.__name__} failed: {e}")

    # remove duplicates
    unique = {}
    for e in all_events:
        unique[e["id"]] = e

    all_events = list(unique.values())

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "events": all_events
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(all_events)} events.")


if __name__ == "__main__":
    main()
