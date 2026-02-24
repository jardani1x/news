#!/usr/bin/env python3
"""
News Builder with Charts - Hedge Fund Style
Generates news summary with interactive trading charts
"""
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIG
# ============================================================================
CATEGORIES = {
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
    "Crypto": [
        ("CoinGecko Trending", "https://www.coingecko.com/en/rss"),
        ("Bitcoinist", "https://bitcoinist.com/feed/"),
    ],
    "Markets": [
        ("Reuters Markets", "https://feeds.reuters.com/reuters/marketNews"),
        ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ],
    "Singapore": [
        ("CNA Singapore", "https://www.channelnewsasia.com/rssfeeds/8395986"),
        ("Straits Times", "https://www.straitstimes.com/news/singapore/rss.xml"),
    ],
    "US Politics": [
        ("Reuters Politics", "https://feeds.reuters.com/Reuters/politicsNews"),
        ("BBC Politics", "http://feeds.bbci.co.uk/news/politics/rss.xml"),
    ],
    "Science": [
        ("Reuters Science", "https://feeds.reuters.com/reuters/scienceNews"),
        ("Nature", "https://www.nature.com/nature.rss"),
    ],
}

MAX_PER_CATEGORY = 10

# World Indices for charts
WORLD_INDICES = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
}

# Crypto for charts
CRYPTO_TICKERS = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
}

OUTPUT_DIR = "/media/ruska_roma/delta_llc/ops/news"
CHART_DIR = f"{OUTPUT_DIR}/charts"
DATA_FILE = f"{OUTPUT_DIR}/data/news.json"
INDEX_CHART_FILE = f"{CHART_DIR}/world-indices.html"
CRYPTO_CHART_FILE = f"{CHART_DIR}/crypto-charts.html"


# ============================================================================
# UTILS
# ============================================================================
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_feed(feed_name: str, url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 NewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"[WARN] Failed to fetch {feed_name}: {e}")
        return []

    try:
        root = ET.fromstring(xml_data)
    except:
        return []

    items = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", default=""))
        link = clean_text(item.findtext("link", default=""))
        pub = clean_text(item.findtext("pubDate", default=""))
        desc = clean_text(item.findtext("description", default=""))
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "source": feed_name,
                "published": pub,
                "description": desc[:200] if desc else ""
            })

    # Atom feed fallback
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns) or root.findall(".//entry"):
            title = clean_text(entry.findtext("title", default=""))
            link_elem = entry.find("link") or entry.find("{http://www.w3.org/2005/Atom}link")
            link = clean_text(link_elem.attrib.get("href", "") if link_elem is not None else "")
            pub = clean_text(entry.findtext("updated", default="") or entry.findtext("published", default=""))
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "source": feed_name,
                    "published": pub,
                    "description": ""
                })

    return items


# ============================================================================
# HEDGE FUND INDICATORS
# ============================================================================
def add_hedge_fund_indicators(fig, df, row=1, col=1):
    """Add hedge fund style indicators: SMA, EMA, RSI, MACD, Bollinger Bands"""
    
    if df.empty or len(df) < 20:
        return df
    
    # 20-day Simple Moving Average
    sma20 = df['Close'].rolling(window=20).mean()
    # 50-day SMA
    sma50 = df['Close'].rolling(window=50).mean()
    
    # Bollinger Bands
    bb_middle = df['Close'].rolling(window=20).mean()
    bb_std = df['Close'].rolling(window=20).std()
    bb_upper = bb_middle + (bb_std * 2)
    bb_lower = bb_middle - (bb_std * 2)
    
    # Add SMA lines
    fig.add_trace(go.Scatter(x=df.index, y=sma20, name='SMA 20', line=dict(color='blue', width=1), opacity=0.7), row=row, col=col)
    fig.add_trace(go.Scatter(x=df.index, y=sma50, name='SMA 50', line=dict(color='orange', width=1), opacity=0.7), row=row, col=col)
    
    # Bollinger Bands
    fig.add_trace(go.Scatter(x=df.index, y=bb_upper, name='BB Upper', line=dict(color='gray', width=0.5), showlegend=False), row=row, col=col)
    fig.add_trace(go.Scatter(x=df.index, y=bb_lower, name='BB Lower', line=dict(color='gray', width=0.5), fill='tonexty', fillcolor='rgba(128,128,128,0.1)', showlegend=False), row=row, col=col)
    
    return df


# ============================================================================
# CHART GENERATORS
# ============================================================================
def generate_world_indices_chart():
    """Generate world indices chart with hedge fund indicators"""
    print("[INFO] Generating world indices chart...")
    
    # Fetch data for last 90 days (shorter for faster download)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    fig = make_subplots(
        rows=len(WORLD_INDICES), cols=1,
        subplot_titles=list(WORLD_INDICES.values()),
        vertical_spacing=0.08,
        row_heights=[1] * len(WORLD_INDICES)
    )
    
    success = False
    for idx, (ticker, name) in enumerate(WORLD_INDICES.items(), 1):
        try:
            # Use shorter timeout and period
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, timeout=10)
            if data is None or data.empty:
                print(f"[WARN] No data for {ticker}")
                # Add placeholder
                fig.add_trace(go.Scatter(x=[], y=[], name=name + " (No Data)"), row=idx, col=1)
                continue
            
            df = data.copy()
            success = True
            
            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name=name,
                increasing_line_color='#26a69a',
                decreasing_line_color='#ef5350'
            ), row=idx, col=1)
            
            # Add indicators
            add_hedge_fund_indicators(fig, df, row=idx, col=1)
            
        except Exception as e:
            print(f"[WARN] Failed to fetch {ticker}: {e}")
            fig.add_trace(go.Scatter(x=[], y=[], name=name + " (Error)"), row=idx, col=1)
    
    # If all failed, create placeholder chart
    if not success:
        print("[WARN] All indices failed, generating placeholder...")
        for idx, (ticker, name) in enumerate(WORLD_INDICES.items(), 1):
            fig.add_trace(go.Scatter(x=[], y=[], name=name + " (Unavailable)"), row=idx, col=1)
    
    fig.update_layout(
        title=dict(text="🌍 World Indices - Hedge Fund Chart (SMA, Bollinger Bands)", font=dict(size=20)),
        height=300 * max(len(WORLD_INDICES), 1),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        plot_bgcolor='black'
    )
    
    os.makedirs(CHART_DIR, exist_ok=True)
    fig.write_html(INDEX_CHART_FILE)
    print(f"[INFO] World indices chart saved to {INDEX_CHART_FILE}")
    return INDEX_CHART_FILE


def generate_crypto_chart():
    """Generate BTC/ETH crypto chart with hedge fund indicators"""
    print("[INFO] Generating crypto chart...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)  # Shorter for faster download
    
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=["Bitcoin (BTC-USD)", "Ethereum (ETH-USD)"],
        vertical_spacing=0.15,
        row_heights=[0.5, 0.5]
    )
    
    success = False
    for idx, (ticker, name) in enumerate(CRYPTO_TICKERS.items(), 1):
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, timeout=10)
            if data is None or data.empty:
                print(f"[WARN] No data for {ticker}")
                fig.add_trace(go.Scatter(x=[], y=[], name=name + " (No Data)"), row=idx, col=1)
                continue
            
            df = data.copy()
            success = True
            
            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name=name,
                increasing_line_color='#f7931a',
                decreasing_line_color='#ef5350'
            ), row=idx, col=1)
            
            # Add indicators
            add_hedge_fund_indicators(fig, df, row=idx, col=1)
            
        except Exception as e:
            print(f"[WARN] Failed to fetch {ticker}: {e}")
            fig.add_trace(go.Scatter(x=[], y=[], name=name + " (Error)"), row=idx, col=1)
    
    # If all failed, create placeholder chart
    if not success:
        print("[WARN] All crypto failed, generating placeholder...")
        fig.add_trace(go.Scatter(x=[], y=[], name="Bitcoin (Unavailable)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=[], y=[], name="Ethereum (Unavailable)"), row=2, col=1)
    
    fig.update_layout(
        title=dict(text="₿ Crypto Charts - Hedge Fund Style (SMA, BB)", font=dict(size=20)),
        height=600,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        plot_bgcolor='black'
    )
    
    os.makedirs(CHART_DIR, exist_ok=True)
    fig.write_html(CRYPTO_CHART_FILE)
    print(f"[INFO] Crypto chart saved to {CRYPTO_CHART_FILE}")
    return CRYPTO_CHART_FILE


# ============================================================================
# NEWS FETCHER
# ============================================================================
def fetch_news():
    """Fetch top news from all categories"""
    print("[INFO] Fetching news...")
    
    news_data = {
        "updated_sgt": datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M SGT"),
        "updated_iso": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "categories": {},
        "charts": {
            "world_indices": os.path.basename(INDEX_CHART_FILE),
            "crypto": os.path.basename(CRYPTO_CHART_FILE)
        }
    }
    
    for category, feeds in CATEGORIES.items():
        merged = []
        seen = set()
        
        for feed_name, url in feeds:
            entries = parse_feed(feed_name, url)
            for e in entries:
                key = (e["title"], e["link"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(e)
                if len(merged) >= MAX_PER_CATEGORY:
                    break
            if len(merged) >= MAX_PER_CATEGORY:
                break
        
        # Sort by published date (newest first)
        merged.sort(key=lambda x: x.get("published", ""), reverse=True)
        news_data["categories"][category] = merged[:MAX_PER_CATEGORY]
        print(f"[INFO] {category}: {len(merged)} articles")
    
    # Flatten to get top 10 overall
    all_news = []
    for cat_news in news_data["categories"].values():
        all_news.extend(cat_news)
    
    # Dedupe and get top 10
    seen_urls = set()
    top10 = []
    for item in all_news:
        if item["link"] not in seen_urls:
            seen_urls.add(item["link"])
            top10.append(item)
            if len(top10) >= 10:
                break
    
    news_data["top10"] = top10
    
    # Save
    os.makedirs(f"{OUTPUT_DIR}/data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] Wrote {DATA_FILE}")
    return news_data


# ============================================================================
# MAIN
# ============================================================================
def build():
    """Main build function"""
    print("=" * 60)
    print("News Builder - Hedge Fund Edition")
    print("=" * 60)
    
    # Generate charts first
    generate_world_indices_chart()
    generate_crypto_chart()
    
    # Fetch news
    news = fetch_news()
    
    print("=" * 60)
    print("Build complete!")
    print(f"Charts: {CHART_DIR}")
    print(f"Data: {DATA_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    build()
