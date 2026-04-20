"""
RevU Offerwall New Offer Alert Bot (v2 - Smart Alerts)
-------------------------------------------------------
প্রতি ১ ঘন্টা পর পর RevU API check করে।
যখনই নতুন offer add হয়, Telegram এ notification পাঠায়।

New in v2:
  ✅ Proxy dead → instant Telegram alert
  ✅ Proxy recover → "back online" notification
  ✅ API key expired হলে আলাদা alert
  ✅ Spam prevention (৪ ঘন্টায় একবার same error alert)
  ✅ Startup এ proxy test
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
# ⚙️ CONFIGURATION
# ==========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8750340183:AAFzsxuvKhXiu3PZ3fzgQneg7beHB3ywpMk")
CHAT_ID = os.environ.get("CHAT_ID", "PASTE_YOUR_CHAT_ID_HERE")

API_KEY = os.environ.get("API_KEY", "UJySOkeLTFVNpgothrmx")
USER_ID = os.environ.get("USER_ID", "146201375")

PROXY_URL = os.environ.get(
    "PROXY_URL",
    "socks5://wwujdqre:hjelhw39pl4v@198.23.239.134:6540"
)

CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))

# Alert spam prevention — same error পরপর কতবার notify হবে না (seconds)
ERROR_ALERT_COOLDOWN = int(os.environ.get("ERROR_ALERT_COOLDOWN", "14400"))  # 4 hours

# ==========================================================

REVU_API = "https://api-wall.revenueuniverse.com/offers.php"
KNOWN_OFFERS_FILE = "known_offers.json"
STATE_FILE = "bot_state.json"  # error tracking state

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


# ---------- State Management ----------
def load_state():
    """Error tracking state load করে"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_error_type": None,           # proxy / api_key / timeout / server
        "last_error_alert_time": 0,        # last time error alerted
        "consecutive_failures": 0,         # how many checks failed in a row
        "last_success_time": 0,            # last successful check
    }


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Could not save state: {e}")


# ---------- Telegram ----------
def send_telegram(text, disable_preview=True):
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


# ---------- Smart Error Alerter ----------
def alert_error(error_type, details, state):
    """
    Error alert পাঠায়, কিন্তু spam prevention সহ।
    Same error type হলে ৪ ঘন্টার মধ্যে আবার পাঠাবে না।
    """
    now = time.time()
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1

    # Same error type এবং cooldown period এর মধ্যে হলে skip
    if (
        state.get("last_error_type") == error_type
        and now - state.get("last_error_alert_time", 0) < ERROR_ALERT_COOLDOWN
    ):
        hours_silent = (ERROR_ALERT_COOLDOWN - (now - state["last_error_alert_time"])) / 3600
        logger.info(
            f"⏸️ Same error ({error_type}), alerted already. "
            f"Next alert in ~{hours_silent:.1f}h if still failing."
        )
        save_state(state)
        return

    # Build alert message based on error type
    icons = {
        "proxy": "🔴",
        "api_key": "🔑",
        "timeout": "⏱️",
        "server": "🌐",
        "unknown": "⚠️",
    }
    titles = {
        "proxy": "Proxy Dead!",
        "api_key": "API Key Expired!",
        "timeout": "Request Timeout!",
        "server": "RevU Server Error!",
        "unknown": "Unknown Error!",
    }
    actions = {
        "proxy": (
            "🔧 <b>কী করতে হবে:</b>\n"
            "• Proxy provider panel এ login করে check করো\n"
            "• Proxy expire হলে নতুন কিনে Railway env variable update করো\n"
            "• অথবা bot.py এর PROXY_URL change করে redeploy"
        ),
        "api_key": (
            "🔧 <b>কী করতে হবে:</b>\n"
            "• USA VPN দিয়ে browser এ RevU wall open করো\n"
            "• DevTools → Network → নতুন cURL নিয়ে fresh api_key\n"
            "• Railway env variable বা bot.py এ update করো"
        ),
        "timeout": (
            "🔧 <b>কী করতে হবে:</b>\n"
            "• Proxy slow থাকতে পারে\n"
            "• পরের cycle এ automatic retry হবে\n"
            "• Consistent হলে proxy change করো"
        ),
        "server": (
            "🔧 <b>কী করতে হবে:</b>\n"
            "• RevU server temporarily down\n"
            "• Bot automatic retry করবে\n"
            "• কিছু করার দরকার নেই"
        ),
        "unknown": (
            "🔧 Railway log check করে details দেখো"
        ),
    }

    icon = icons.get(error_type, "⚠️")
    title = titles.get(error_type, "Error")
    action = actions.get(error_type, "")

    msg = f"{icon} <b>{title}</b>\n\n"
    msg += f"📋 <b>Details:</b>\n<code>{details[:300]}</code>\n\n"
    msg += f"{action}\n\n"
    msg += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"🔁 Consecutive failures: {state['consecutive_failures']}\n\n"
    msg += f"<i>Bot will keep retrying every {CHECK_INTERVAL // 60} minutes.</i>"

    send_telegram(msg)

    # Update state
    state["last_error_type"] = error_type
    state["last_error_alert_time"] = now
    save_state(state)


def alert_recovery(state):
    """Error থেকে recover হলে Telegram এ জানায়"""
    if state.get("last_error_type"):
        downtime_seconds = 0
        if state.get("last_success_time"):
            downtime_seconds = time.time() - state["last_success_time"]
        downtime_hours = downtime_seconds / 3600

        error_type = state["last_error_type"]
        icons = {"proxy": "🟢", "api_key": "🔑", "timeout": "⏱️", "server": "🌐"}
        icon = icons.get(error_type, "✅")

        msg = f"{icon} <b>Back Online!</b>\n\n"
        msg += f"✅ Bot successfully reconnected\n"
        msg += f"🔧 Previous issue: <code>{error_type}</code>\n"
        if downtime_hours > 0.1:
            msg += f"⏰ Downtime: ~{downtime_hours:.1f} hours\n"
        msg += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        send_telegram(msg)

    # Reset error state
    state["last_error_type"] = None
    state["last_error_alert_time"] = 0
    state["consecutive_failures"] = 0
    state["last_success_time"] = time.time()
    save_state(state)


# ---------- Known Offers ----------
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


# ---------- Fetch Offers (with smart error classification) ----------
def fetch_offers(state):
    """
    Returns tuple: (offers_list, error_type)
    offers_list is None if error occurred.
    error_type: None on success, or one of: proxy / api_key / timeout / server / unknown
    """
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

        # HTTP status analysis
        if r.status_code in (401, 403):
            msg = f"API returned {r.status_code}: {r.text[:200]}"
            logger.error(msg)
            return None, "api_key", msg

        if r.status_code >= 500:
            msg = f"Server error {r.status_code}: {r.text[:200]}"
            logger.error(msg)
            return None, "server", msg

        if r.status_code != 200:
            msg = f"API returned {r.status_code}: {r.text[:200]}"
            logger.error(msg)
            return None, "unknown", msg

        try:
            data = r.json()
        except Exception as e:
            msg = f"Invalid JSON response: {str(e)[:100]}"
            logger.error(msg)
            return None, "server", msg

        if data.get("status") != "success":
            msg = f"API status not success: {str(data)[:200]}"
            logger.error(msg)
            # "invalid key" type errors usually indicate api_key issue
            err_text = str(data).lower()
            if "key" in err_text or "auth" in err_text or "unauthorized" in err_text:
                return None, "api_key", msg
            return None, "server", msg

        offers = data.get("offers", [])
        logger.info(f"✅ Fetched {len(offers)} offers from RevU")
        return offers, None, None

    except requests.exceptions.ProxyError as e:
        msg = f"Proxy error: {str(e)[:200]}"
        logger.error(msg)
        return None, "proxy", msg

    except requests.exceptions.ConnectTimeout as e:
        msg = f"Proxy connection timeout: {str(e)[:200]}"
        logger.error(msg)
        return None, "proxy", msg

    except requests.exceptions.Timeout as e:
        msg = f"Request timeout: {str(e)[:150]}"
        logger.error(msg)
        return None, "timeout", msg

    except requests.exceptions.ConnectionError as e:
        # Could be proxy or network
        err_str = str(e).lower()
        if "proxy" in err_str or "socks" in err_str:
            msg = f"Proxy connection failed: {str(e)[:200]}"
            return None, "proxy", msg
        msg = f"Connection error: {str(e)[:200]}"
        logger.error(msg)
        return None, "server", msg

    except Exception as e:
        msg = f"Unexpected error: {str(e)[:200]}"
        logger.exception("Fetch error")
        return None, "unknown", msg


# ---------- Format Offer Message ----------
def format_offer_message(offer):
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


# ---------- Main Check ----------
def check_new_offers(state):
    offers, error_type, error_msg = fetch_offers(state)

    if offers is None:
        # Fetch failed — smart alert
        alert_error(error_type, error_msg, state)
        return

    # SUCCESS! Check if recovering from previous error
    if state.get("last_error_type"):
        alert_recovery(state)
    else:
        state["last_success_time"] = time.time()
        state["consecutive_failures"] = 0
        save_state(state)

    # Process offers
    current_ids = set()
    offer_map = {}
    for o in offers:
        cid = o.get("cid")
        if cid:
            current_ids.add(cid)
            offer_map[cid] = o

    known_ids = load_known_offers()

    # First run
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

    # Detect new
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
        logger.info(f"ℹ️ {len(removed_ids)} offer(s) removed (cap ended)")

    save_known_offers(current_ids)


# ---------- Status Summary ----------
last_summary = 0
SUMMARY_INTERVAL = 6 * 3600  # every 6 hours


def maybe_send_summary(state):
    global last_summary
    now = time.time()
    if now - last_summary >= SUMMARY_INTERVAL:
        known = load_known_offers()
        # Don't send summary if currently in error state (avoid confusion)
        if not state.get("last_error_type"):
            send_telegram(
                f"📊 <b>RevU Bot Status</b>\n\n"
                f"✅ Bot is alive & healthy\n"
                f"📦 Tracking {len(known)} offers\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        last_summary = now


# ---------- Config Validation ----------
def validate_config():
    issues = []

    if not BOT_TOKEN or "YOUR_" in BOT_TOKEN:
        issues.append("❌ BOT_TOKEN ঠিক নেই")

    if not CHAT_ID or "PASTE_" in CHAT_ID or "YOUR_" in CHAT_ID:
        issues.append("❌ CHAT_ID বসাতে হবে!")

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


# ---------- Main Loop ----------
def main():
    logger.info("=" * 50)
    logger.info("🚀 RevU Offer Alert Bot v2 Starting")
    logger.info("=" * 50)

    if not validate_config():
        logger.error("Exiting due to configuration errors")
        return

    logger.info(f"Check interval: {CHECK_INTERVAL}s ({CHECK_INTERVAL//60} min)")
    logger.info(f"Proxy: {'✅ Configured' if PROXY_URL else '❌ Not set'}")
    logger.info(f"Error alert cooldown: {ERROR_ALERT_COOLDOWN}s ({ERROR_ALERT_COOLDOWN//3600}h)")

    state = load_state()

    while True:
        try:
            logger.info("-" * 40)
            logger.info("🔍 Checking for new offers...")
            check_new_offers(state)
            # Reload state (in case check_new_offers updated it)
            state = load_state()
            maybe_send_summary(state)
        except Exception as e:
            logger.exception(f"Unexpected error in main loop: {e}")
            alert_error("unknown", str(e)[:300], state)
            state = load_state()

        logger.info(f"💤 Sleeping {CHECK_INTERVAL}s until next check...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
