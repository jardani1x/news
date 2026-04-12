#!/usr/bin/env python3
"""
Webhook Notifier - Discord & Telegram
Sends a formatted news summary after each build.

Environment variables:
  DISCORD_WEBHOOK_URL   - Discord incoming webhook URL
  TELEGRAM_BOT_TOKEN    - Telegram bot token
  TELEGRAM_CHAT_ID      - Telegram chat / channel ID
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

MAX_RETRIES = 4
INITIAL_BACKOFF = 2  # seconds (doubles each attempt: 2, 4, 8, 16)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _post_json(url: str, payload: dict, headers: dict | None = None) -> bool:
    """POST JSON payload to a URL with retry / exponential backoff."""
    body = json.dumps(payload).encode("utf-8")
    default_headers = {
        "Content-Type": "application/json",
        "User-Agent": "NewsBot/1.0",
    }
    if headers:
        default_headers.update(headers)

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=body, headers=default_headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.getcode()
                if 200 <= status < 300:
                    return True
                print(f"[NOTIFIER] HTTP {status} from {url}")
        except urllib.error.HTTPError as e:
            print(f"[NOTIFIER] HTTP error {e.code}: {e.reason}")
        except Exception as e:
            print(f"[NOTIFIER] Request error: {e}")

        if attempt < MAX_RETRIES - 1:
            wait = INITIAL_BACKOFF * (2 ** attempt)
            print(f"[NOTIFIER] Retry {attempt + 1}/{MAX_RETRIES - 1} in {wait}s…")
            time.sleep(wait)

    return False


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ============================================================================
# DISCORD
# ============================================================================

def send_discord(webhook_url: str, news_data: dict) -> bool:
    """Send a rich embed to a Discord webhook."""
    now_sgt = news_data.get("updated_sgt", datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M SGT"))
    top10 = news_data.get("top10", [])

    lines = []
    for i, item in enumerate(top10[:10], 1):
        title = _truncate(item.get("title", "(no title)"), 90)
        link = item.get("link", "")
        source = item.get("source", "")
        line = f"{i}. [{title}]({link})"
        if source:
            line += f" — *{source}*"
        lines.append(line)

    description = "\n".join(lines) if lines else "No headlines available."

    payload = {
        "embeds": [
            {
                "title": "Daily News Update",
                "description": _truncate(description, 4096),
                "color": 0x2F3136,
                "footer": {"text": f"Updated {now_sgt}"},
                "url": "https://jardani1x.github.io/news/",
            }
        ]
    }

    ok = _post_json(webhook_url, payload)
    if ok:
        print("[NOTIFIER] Discord notification sent.")
    else:
        print("[NOTIFIER] Discord notification FAILED after all retries.")
    return ok


# ============================================================================
# TELEGRAM
# ============================================================================

def send_telegram(bot_token: str, chat_id: str, news_data: dict) -> bool:
    """Send a Markdown message via Telegram Bot API."""
    now_sgt = news_data.get("updated_sgt", datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M SGT"))
    top10 = news_data.get("top10", [])

    lines = [f"*Daily News Update* — {now_sgt}", ""]
    for i, item in enumerate(top10[:10], 1):
        title = _truncate(item.get("title", "(no title)"), 100)
        link = item.get("link", "")
        source = item.get("source", "")
        # Escape Markdown special chars in title
        safe_title = title.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
        if link:
            line = f"{i}\\. [{safe_title}]({link})"
        else:
            line = f"{i}\\. {safe_title}"
        if source:
            line += f" _({source})_"
        lines.append(line)

    lines += ["", "[View full news →](https://jardani1x.github.io/news/)"]
    text = "\n".join(lines)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": _truncate(text, 4096),
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }

    ok = _post_json(url, payload)
    if ok:
        print("[NOTIFIER] Telegram notification sent.")
    else:
        print("[NOTIFIER] Telegram notification FAILED after all retries.")
    return ok


# ============================================================================
# PUBLIC API
# ============================================================================

def notify(news_data: dict) -> None:
    """
    Send news update notifications to all configured platforms.

    Reads configuration from environment variables:
      DISCORD_WEBHOOK_URL
      TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
    """
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    sent_any = False

    if discord_url:
        send_discord(discord_url, news_data)
        sent_any = True
    else:
        print("[NOTIFIER] DISCORD_WEBHOOK_URL not set — skipping Discord.")

    if tg_token and tg_chat:
        send_telegram(tg_token, tg_chat, news_data)
        sent_any = True
    elif tg_token or tg_chat:
        print("[NOTIFIER] Both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required — skipping Telegram.")
    else:
        print("[NOTIFIER] Telegram credentials not set — skipping Telegram.")

    if not sent_any:
        print("[NOTIFIER] No notification platforms configured.")
