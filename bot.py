"""
RevU Offerwall New Offer Alert Bot
-----------------------------------
প্রতি ১ ঘন্টা পর পর RevU API check করে।
যখনই নতুন offer add হয়, Telegram এ notification পাঠায়।
"""

import os
import json
import time
import logging
import requests
from datetime import datetime

# ---------- Logging Setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("RevUBot")

# ==========================================================
# ⚙️ CONFIGURATION — তোমার info এখানে বসানো আছে
# চাইলে Railway এ Environment Variables এ move করতে পারো,
# বা এখানেই change করে নিতে পারো।
# ==========================================================

# --- Telegram ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8750340183:AAFzsxuvKhXiu3PZ3fzgQneg7beHB3ywpMk")

# ⚠️ CHAT_ID তুমি দাওনি! এখানে তোমার Telegram group/chat ID বসাও
# Group এর জন্য negative number হবে (যেমন: -1001234567890)
CHAT_ID = os.environ.get("CHAT_ID", "PASTE_YOUR_CHAT_ID_HERE")

# --- RevU API ---
API_KEY = os.environ.get("API_KEY", "UJySOkeLTFVNpgothrmx")
USER_ID = os.environ.get("USER_ID", "146201375")

# --- USA SOCKS5 Proxy ---
PROXY_URL = os.environ.get(
    "PROXY_URL",
    "socks5://wwujdqre:hjelhw39pl4v@198.23.239.134:6540"
)

# --- Check Interval (seconds) — 3600 = 1 hour ---
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))

# ==========================================================
# এর নিচের কিছু change করার দরকার নাই
# ==========================================================

REVU_API = "https://api-wall.revenueuniverse.com/offers.php"
KNOWN_OFFERS_FILE = "known_offers.json"

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://wall.revenueuniverse.com",
    "Referer": "https://wall.revenueuniverse.com/784/offers/eikhne",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def send_telegram(text, disable_preview=True):
    """Telegram এ message পাঠায়"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200:
            logger.info("✅ Telegram message sent")
            return True
        else:
            logger.error(f"Telegram failed: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def load_known_offers():
    if os.path.exists(KNOWN_OFFERS_FILE):
        try:
            with open(KNOWN_OFFERS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logger.warning(f"Could not load known offers: {e}")
    return set()


def save_known_offers(offer_ids):
    try:
        with open(KNOWN_OFFERS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(offer_ids), f)
    except Exception as e:
        logger.error(f"Could not save known offers: {e}")


def fetch_offers():
    """RevU API থেকে current offer list আনে"""
    params = {
        "api_key": API_KEY,
        "id": USER_ID,
        "type": "desktop",
    }

    proxies = None
    if PROXY_URL:
        proxies = {"http": PROXY_URL, "https": PROXY_URL}

    try:
        r = requests.get(
            REVU_API,
            params=params,
            headers=HEADERS,
            proxies=proxies,
            timeout=60,
        )

        if r.status_code != 200:
            logger.error(f"API returned {r.status_code}: {r.text[:200]}")
            return None

        data = r.json()

        if data.get("status") != "success":
            logger.error(f"API status not success: {data}")
            return None

        offers = data.get("offers", [])
        logger.info(f"✅ Fetched {len(offers)} offers from RevU")
        return offers

    except requests.exceptions.ProxyError as e:
        logger.error(f"Proxy error: {e}")
        return None
    except requests.exceptions.Timeout:
        logger.error("Request timeout")
        return None
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return None


def format_offer_message(offer):
    """সুন্দর HTML format এ offer details বানায়"""
    name = offer.get("name", "Unknown")
    description = offer.get("description", "")
    category = offer.get("category", "N/A")
    currency = offer.get("currency", 0)
    url = offer.get("url", "")
    terms = offer.get("terms", "")
    featured = offer.get("featured", False)

    def esc(s):
        if not s:
            return ""
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    fire = "🔥 " if featured else ""
    msg = f"🎯 <b>New Offer on RevU!</b>\n\n"
    msg += f"{fire}<b>{esc(name)}</b>\n\n"
    msg += f"💰 <b>Currency:</b> {currency:,} points\n"
    msg += f"🏷️ <b>Category:</b> {esc(category)}\n\n"

    if description:
        desc_short = description[:300] + "..." if len(description) > 300 else description
        msg += f"📝 {esc(desc_short)}\n\n"

    if terms:
        terms_short = terms[:200] + "..." if len(terms) > 200 else terms
        msg += f"📋 <b>Terms:</b> {esc(terms_short)}\n\n"

    if url:
        msg += f'🔗 <a href="{url}">Click to do offer</a>'

    return msg


def check_new_offers():
    """Main check — compares current offers with known, sends alerts"""
    offers = fetch_offers()
    if offers is None:
        logger.warning("Skipping this check due to fetch error")
        return

    current_ids = set()
    offer_map = {}
    for o in offers:
        cid = o.get("cid")
        if cid:
            current_ids.add(cid)
            offer_map[cid] = o

    known_ids = load_known_offers()

    if not known_ids:
        logger.info(f"First run — saving {len(current_ids)} offers as baseline")
        save_known_offers(current_ids)
        send_telegram(
            f"🤖 <b>RevU Bot Started</b>\n\n"
            f"📊 Tracking {len(current_ids)} current offers\n"
            f"⏰ Check interval: {CHECK_INTERVAL // 60} minutes\n\n"
            f"নতুন offer আসলেই এখানে notification পাবে।"
        )
        return

    new_ids = current_ids - known_ids
    removed_ids = known_ids - current_ids

    if new_ids:
        logger.info(f"🎉 Found {len(new_ids)} NEW offer(s)!")
        for new_cid in new_ids:
            offer = offer_map[new_cid]
            msg = format_offer_message(offer)
            send_telegram(msg, disable_preview=False)
            time.sleep(2)
    else:
        logger.info("No new offers this time")

    if removed_ids:
        logger.info(f"ℹ️ {len(removed_ids)} offer(s) removed (likely cap ended)")

    save_known_offers(current_ids)


last_summary = 0
SUMMARY_INTERVAL = 6 * 3600


def maybe_send_summary():
    global last_summary
    now = time.time()
    if now - last_summary >= SUMMARY_INTERVAL:
        known = load_known_offers()
        send_telegram(
            f"📊 <b>RevU Bot Status</b>\n\n"
            f"✅ Bot is alive\n"
            f"📦 Tracking {len(known)} offers\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        last_summary = now


def validate_config():
    issues = []

    if not BOT_TOKEN or "YOUR_" in BOT_TOKEN:
        issues.append("❌ BOT_TOKEN ঠিক নেই")

    if not CHAT_ID or "PASTE_" in CHAT_ID or "YOUR_" in CHAT_ID:
        issues.append("❌ CHAT_ID বসাতে হবে! bot.py এর ২২ নং line এ।")

    if not API_KEY or "YOUR_" in API_KEY:
        issues.append("❌ API_KEY ঠিক নেই")

    if not PROXY_URL:
        logger.warning("⚠️ PROXY_URL not set — USA offers নাও আসতে পারে")

    if issues:
        logger.error("Configuration issues:")
        for i in issues:
            logger.error(f"   {i}")
        return False
    return True


def main():
    logger.info("=" * 50)
    logger.info("🚀 RevU Offer Alert Bot Starting")
    logger.info("=" * 50)

    if not validate_config():
        logger.error("Exiting due to configuration errors")
        return

    logger.info(f"Check interval: {CHECK_INTERVAL}s ({CHECK_INTERVAL//60} min)")
    logger.info(f"Proxy: {'✅ Configured' if PROXY_URL else '❌ Not set'}")

    while True:
        try:
            logger.info("-" * 40)
            logger.info("🔍 Checking for new offers...")
            check_new_offers()
            maybe_send_summary()
        except Exception as e:
            logger.exception(f"Unexpected error in main loop: {e}")
            try:
                send_telegram(f"⚠️ <b>Bot Error</b>\n<code>{str(e)[:300]}</code>")
            except:
                pass

        logger.info(f"💤 Sleeping {CHECK_INTERVAL}s until next check...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

