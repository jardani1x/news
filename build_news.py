#!/usr/bin/env python3
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

TOPICS = {
    "World": [
        ("Reuters World", "https://feeds.reuters.com/Reuters/worldNews"),
        ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ],
    "Finance": [
        ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
        ("CNBC Finance", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ],
    "Technology": [
        ("Reuters Technology", "https://feeds.reuters.com/reuters/technologyNews"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ],
    "Local Singapore": [
        ("CNA Singapore", "https://www.channelnewsasia.com/rssfeeds/8395986"),
        ("Straits Times Singapore", "https://www.straitstimes.com/news/singapore/rss.xml"),
    ],
}

MAX_PER_TOPIC = 8


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_feed(feed_name: str, url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 NewsBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_data = resp.read()

    root = ET.fromstring(xml_data)
    items = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", default=""))
        link = clean_text(item.findtext("link", default=""))
        pub = clean_text(item.findtext("pubDate", default=""))
        if title and link:
            items.append({"title": title, "link": link, "source": feed_name, "published": pub})

    if not items:
        ns_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in ns_items:
            title = clean_text(entry.findtext("{http://www.w3.org/2005/Atom}title", default=""))
            link_elem = entry.find("{http://www.w3.org/2005/Atom}link")
            link = clean_text(link_elem.attrib.get("href", "") if link_elem is not None else "")
            pub = clean_text(entry.findtext("{http://www.w3.org/2005/Atom}updated", default=""))
            if title and link:
                items.append({"title": title, "link": link, "source": feed_name, "published": pub})

    return items


def build_news_data():
    payload = {
        "updated_sgt": datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M SGT"),
        "topics": {},
    }

    for topic, feeds in TOPICS.items():
        merged = []
        seen = set()

        for feed_name, url in feeds:
            try:
                entries = parse_feed(feed_name, url)
            except Exception as e:
                print(f"[WARN] Failed to fetch {feed_name}: {e}")
                continue

            for e in entries:
                key = (e["title"], e["link"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(e)
                if len(merged) >= MAX_PER_TOPIC:
                    break
            if len(merged) >= MAX_PER_TOPIC:
                break

        payload["topics"][topic] = merged

    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("Wrote data/news.json")


if __name__ == "__main__":
    build_news_data()
