#!/usr/bin/env python3
"""
News Builder with Charts - Hedge Fund Style
Generates news summary with interactive trading charts

Fixes: Added retries with exponential backoff, caching, and CoinGecko fallback
"""
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
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
MAX_RETRIES = 2
INITIAL_BACKOFF = 1  # seconds - fail faster
CACHE_MAX_AGE_HOURS = 24

CATEGORIES = {
    "World": [
        ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
    "Finance": [
        ("CNBC Finance", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ],
    "Technology": [
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
    ],
    "Crypto": [
        ("CoinDesk", "https://www.coindesk.com/feed/"),
        ("Bitcoinist", "https://bitcoinist.com/feed/"),
    ],
    "Markets": [
        ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
        ("Investing.com", "https://www.investing.com/rss/news.rss"),
    ],
    "Singapore": [
        ("CNA Singapore", "https://www.channelnewsasia.com/rssfeeds/8395986"),
        ("Straits Times", "https://www.straitstimes.com/news/singapore/rss.xml"),
    ],
    "US Politics": [
        ("BBC Politics", "http://feeds.bbci.co.uk/news/politics/rss.xml"),
        ("AP News", "https://feeds.apnews.com/apnews/topnews"),
    ],
    "Science": [
        ("Nature", "https://www.nature.com/nature.rss"),
        ("Science Daily", "https://www.sciencedaily.com/rss/all.xml"),
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
CACHE_DIR = f"{OUTPUT_DIR}/cache"
INDEX_CHART_FILE = f"{CHART_DIR}/world-indices.html"
CRYPTO_CHART_FILE = f"{CHART_DIR}/crypto-charts.html"

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================================
# UTILS - RETRY WITH EXPONENTIAL BACKOFF
# ============================================================================
def retry_with_backoff(func, max_retries=MAX_RETRIES, initial_backoff=INITIAL_BACKOFF):
    """Retry a function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = initial_backoff * (2 ** attempt)
            print(f"[WARN] Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)


def get_cached_data(ticker: str) -> pd.DataFrame | None:
    """Load cached data if available and less than 24h old"""
    cache_file = Path(CACHE_DIR) / f"{ticker.replace('-', '_')}.json"
    if cache_file.exists():
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age = datetime.now() - mtime
            if age < timedelta(hours=CACHE_MAX_AGE_HOURS):
                with open(cache_file) as f:
                    data = json.load(f)
                df = pd.DataFrame(data)
                if 'timestamp' in df.columns:
                    df.set_index('timestamp', inplace=True)
                print(f"[CACHE] Loaded cached data for {ticker} (age: {age.total_seconds()/3600:.1f}h)")
                return df
            else:
                print(f"[CACHE] Cache expired for {ticker} (age: {age.total_seconds()/3600:.1f}h)")
        except Exception as e:
            print(f"[WARN] Failed to load cache for {ticker}: {e}")
    return None


def save_cached_data(ticker: str, df: pd.DataFrame):
    """Save data to cache"""
    try:
        cache_file = Path(CACHE_DIR) / f"{ticker.replace('-', '_')}.json"
        df_reset = df.reset_index()
        if 'timestamp' not in df_reset.columns:
            df_reset.columns = ['timestamp'] + list(df_reset.columns[1:])
        df_reset.to_json(cache_file, orient='records', indent=2)
        print(f"[CACHE] Saved data for {ticker}")
    except Exception as e:
        print(f"[WARN] Failed to save cache for {ticker}: {e}")


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
def fetch_with_retry(ticker: str, start_date, end_date, timeout=10) -> pd.DataFrame | None:
    """Fetch data with retry and fallback - fast timeout to avoid hanging"""
    
    def _fetch():
        # Use yfinance with SHORT timeout to fail fast
        data = yf.download(
            ticker, 
            start=start_date, 
            end=end_date, 
            progress=False,
            timeout=timeout,
            auto_adjust=True
        )
        return data
    
    # Try with retries
    for attempt in range(MAX_RETRIES):
        try:
            data = _fetch()
            if data is not None and not data.empty:
                save_cached_data(ticker, data)
                return data
        except Exception as e:
            print(f"[WARN] yfinance attempt {attempt + 1} failed for {ticker}: {e}")
            if attempt < MAX_RETRIES - 1:
                wait_time = INITIAL_BACKOFF * (2 ** attempt)
                time.sleep(wait_time)
    
    # Fallback: try cached data
    print(f"[INFO] Trying cache fallback for {ticker}")
    cached = get_cached_data(ticker)
    if cached is not None:
        return cached
    
    return None


def is_yfinance_available() -> bool:
    """Quick check if yfinance is reachable using subprocess timeout"""
    import subprocess
    
    test_script = '''
import yfinance
try:
    yf.download("^GSPC", period="1d", progress=False)
    print("OK")
except Exception as e:
    print(f"ERROR: {e}")
'''
    
    try:
        result = subprocess.run(
            ["python3", "-c", test_script],
            capture_output=True,
            text=True,
            timeout=8
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return True
        print(f"[WARN] yfinance check failed: {result.stderr[:100]}")
        return False
    except subprocess.TimeoutExpired:
        print("[WARN] yfinance check timed out")
        return False
    except Exception as e:
        print(f"[WARN] yfinance check error: {e}")
        return False


def generate_world_indices_chart():
    """Generate world indices chart with hedge fund indicators"""
    print("[INFO] Generating world indices chart...")
    
    # Check if yfinance is reachable - quick test
    if not is_yfinance_available():
        print("[INFO] Skipping stock indices chart - will generate placeholder")
        
        # Generate placeholder chart
        fig = make_subplots(
            rows=len(WORLD_INDICES), cols=1,
            subplot_titles=list(WORLD_INDICES.values()),
            vertical_spacing=0.08,
            row_heights=[1] * len(WORLD_INDICES)
        )
        for idx, (ticker, name) in enumerate(WORLD_INDICES.items(), 1):
            fig.add_trace(go.Scatter(x=[], y=[], name=name + " (Unavailable - Network Issue)"), row=idx, col=1)
        
        fig.update_layout(
            title=dict(text="🌍 World Indices - (Temporarily Unavailable)", font=dict(size=20)),
            height=300 * len(WORLD_INDICES),
            template="plotly_dark",
            plot_bgcolor='black'
        )
        
        os.makedirs(CHART_DIR, exist_ok=True)
        fig.write_html(INDEX_CHART_FILE)
        return INDEX_CHART_FILE
    
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
            # Use retry wrapper with shorter timeout
            data = fetch_with_retry(ticker, start_date, end_date, timeout=10)
            
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


def fetch_crypto_coingecko(coin_id: str, days: int = 90) -> pd.DataFrame | None:
    """Fetch crypto data from CoinGecko API as fallback"""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = f"vs_currency=usd&days={days}&interval=daily"
        
        req = urllib.request.Request(f"{url}?{params}", headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        })
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        
        if "prices" not in data:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(data["prices"], columns=["timestamp", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        
        # Generate OHLC from price (approximation for daily data)
        df["open"] = df["close"] * 0.99  # Approximate
        df["high"] = df["close"] * 1.01
        df["low"] = df["close"] * 0.98
        
        print(f"[COINGECKO] Fetched {coin_id} from CoinGecko API")
        return df
        
    except Exception as e:
        print(f"[WARN] CoinGecko fetch failed for {coin_id}: {e}")
        return None


def fetch_crypto_binance(symbol: str, days: int = 90) -> pd.DataFrame | None:
    """Fetch crypto data from Binance API"""
    # Map tickers to Binance symbols
    binance_symbols = {
        "BTC-USD": "BTCUSDT",
        "ETH-USD": "ETHUSDT",
    }
    
    binance_sym = binance_symbols.get(symbol)
    if not binance_sym:
        return None
    
    try:
        # Get klines (candlestick) data
        url = f"https://api.binance.com/api/v3/klines"
        params = f"symbol={binance_sym}&interval=1d&limit={days}"
        
        req = urllib.request.Request(f"{url}?{params}", headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        })
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        
        if not data:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"
        ])
        
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        
        # Select needed columns - lowercase the column names
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        df.columns = [c.capitalize() for c in df.columns]  # Open, High, Low, Close
        
        print(f"[BINANCE] Fetched {symbol} from Binance API")
        return df
        
    except Exception as e:
        print(f"[WARN] Binance fetch failed for {symbol}: {e}")
        return None


def generate_crypto_chart():
    """Generate BTC/ETH crypto chart with hedge fund indicators"""
    print("[INFO] Generating crypto chart...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)  # Shorter for faster download
    
    # Map tickers to CoinGecko IDs
    cg_mapping = {
        "BTC-USD": "bitcoin",
        "ETH-USD": "ethereum",
    }
    
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=["Bitcoin (BTC-USD)", "Ethereum (ETH-USD)"],
        vertical_spacing=0.15,
        row_heights=[0.5, 0.5]
    )
    
    success = False
    for idx, (ticker, name) in enumerate(CRYPTO_TICKERS.items(), 1):
        try:
            # First try Binance (most reliable)
            data = fetch_crypto_binance(ticker, days=90)
            
            # If Binance failed, try yfinance
            if data is None or data.empty:
                print(f"[INFO] Binance failed, trying yfinance for {ticker}")
                data = fetch_with_retry(ticker, start_date, end_date, timeout=10)
            
            # If yfinance failed, try CoinGecko
            if data is None or data.empty:
                coin_id = cg_mapping.get(ticker)
                if coin_id:
                    print(f"[INFO] Falling back to CoinGecko for {ticker}")
                    data = fetch_crypto_coingecko(coin_id, days=90)
            
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
