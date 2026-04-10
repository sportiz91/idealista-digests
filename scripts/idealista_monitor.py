#!/usr/bin/env python3
"""Idealista private-owner rental monitor → Telegram bot."""

import json
import os
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Config (from env vars)
# ---------------------------------------------------------------------------
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
APIFY_ACTOR_ID = os.environ.get("APIFY_ACTOR_ID", "memo23~idealista-scraper")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SEARCH_URL = os.environ.get("SEARCH_URL", "")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "50"))
MONITORING_MODE = os.environ.get("MONITORING_MODE", "true").lower() == "true"

STATE_FILE = os.environ.get("STATE_FILE", "state/seen_ids.json")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
LOCAL_JSON_INPUT = os.environ.get("LOCAL_JSON_INPUT", "")


# ---------------------------------------------------------------------------
# Apify — call the scraper and get dataset items in one sync call
# ---------------------------------------------------------------------------
def run_apify_actor():
    """Call Apify run-sync-get-dataset-items. Returns list of listings."""
    if LOCAL_JSON_INPUT:
        print(f"[dev] Reading listings from local file: {LOCAL_JSON_INPUT}")
        with open(LOCAL_JSON_INPUT) as f:
            return json.load(f)

    if not APIFY_TOKEN:
        print("ERROR: APIFY_TOKEN not set (and no LOCAL_JSON_INPUT)", file=sys.stderr)
        sys.exit(1)
    if not SEARCH_URL:
        print("ERROR: SEARCH_URL not set", file=sys.stderr)
        sys.exit(1)

    url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}"
        f"/run-sync-get-dataset-items?token={APIFY_TOKEN}"
    )
    payload = {
        "startUrls": [{"url": SEARCH_URL}],
        "maxItems": MAX_ITEMS,
        "monitoringMode": MONITORING_MODE,
    }

    print(f"Calling Apify actor {APIFY_ACTOR_ID}...")
    print(f"  maxItems={MAX_ITEMS}, monitoringMode={MONITORING_MODE}")

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            items = json.loads(resp.read())
            print(f"  Received {len(items)} items from actor")
            return items
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"ERROR: Apify HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Apify connection failed: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Filter: only private-owner listings
# ---------------------------------------------------------------------------
def filter_private(items):
    out = []
    for item in items:
        ci = item.get("contactInfo") or {}
        if ci.get("userType") == "private":
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# State: dedup + daily status counters (committed to repo)
# ---------------------------------------------------------------------------
def _empty_state():
    return {
        "seen_ids": [],
        "count": 0,
        "updated_at": None,
        "last_daily_status_date": None,
        "new_count_today": 0,
        "new_count_yesterday": 0,
    }


def load_state():
    """Load state dict. Returns (state, bootstrap_bool).

    bootstrap_bool is True only when the state file does not exist yet,
    i.e. the very first run of the monitor. It's used to suppress the
    spam of 10-20 initial listings that are already old by the time we
    start tracking.
    """
    if not os.path.exists(STATE_FILE):
        return _empty_state(), True
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        merged = _empty_state()
        merged.update(data)
        return merged, False
    except (json.JSONDecodeError, KeyError):
        print(f"  Corrupt state file {STATE_FILE}, starting fresh")
        return _empty_state(), True


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["seen_ids"] = sorted(set(str(x) for x in state.get("seen_ids", [])))
    state["count"] = len(state["seen_ids"])
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------
def _escape_html(text):
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _clean_url(url):
    return url.split("?")[0] if url else ""


def format_listing(item):
    """Build the Telegram HTML caption for a listing."""
    price = item.get("price", "?")
    basic = item.get("basicInfo") or {}
    more = item.get("moreCharacteristics") or {}
    ubic = item.get("ubication") or {}
    ci = item.get("contactInfo") or {}

    size = basic.get("size") or "?"
    rooms = more.get("roomNumber")
    baths = more.get("bathNumber")
    floor = basic.get("floor") or ""
    is_exterior = bool(more.get("exterior"))

    header_parts = [f"<b>{price}€/mes</b>"]
    if size != "?":
        header_parts.append(f"{size}m²")
    if rooms is not None:
        header_parts.append(f"{rooms} hab" if rooms > 0 else "estudio")
    if baths:
        header_parts.append(f"{baths} baño{'s' if baths > 1 else ''}")
    if floor:
        header_parts.append(f"planta {_escape_html(str(floor))}")
    if is_exterior:
        header_parts.append("☀️ ext")
    header = "🏠 " + " · ".join(header_parts)

    location_bits = [ubic.get("title")]
    for lvl in ("administrativeAreaLevel5", "administrativeAreaLevel4", "administrativeAreaLevel3"):
        v = ubic.get(lvl)
        if v and v not in location_bits:
            location_bits.append(v)
    location = " · ".join(_escape_html(b) for b in location_bits if b)

    contact_name = _escape_html(ci.get("contactName") or "Particular")

    comment = item.get("propertyComment") or ""
    comment = comment.strip()
    if len(comment) > 400:
        comment = comment[:400].rsplit(" ", 1)[0] + "…"
    comment = _escape_html(comment)

    url = _clean_url(item.get("detailWebLink", ""))

    lines = [
        header,
        f"📍 {location}" if location else "",
        f"👤 <b>{contact_name}</b> (particular ✅)",
        "",
    ]
    if comment:
        lines.append(f"<i>{comment}</i>")
        lines.append("")
    lines.append(f'<a href="{url}">📎 Ver en Idealista →</a>')

    return "\n".join(l for l in lines if l != "")


def get_thumbnail(item):
    basic = item.get("basicInfo") or {}
    thumb = basic.get("thumbnail")
    if thumb:
        return thumb
    mm = item.get("multimedia") or {}
    images = mm.get("images") or []
    if images and isinstance(images, list):
        first = images[0]
        if isinstance(first, dict):
            return first.get("url")
    return None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def send_telegram_photo(photo_url, caption):
    """Send a photo with HTML caption. Falls back to text message if no photo."""
    if DRY_RUN or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("---")
        print(caption)
        print(f"  (photo: {photo_url})" if photo_url else "  (no photo)")
        return True

    # Telegram caption limit is 1024 chars
    if len(caption) > 1024:
        caption = caption[:1020] + "…"

    if photo_url:
        endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        }
    else:
        endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                print(f"  Telegram error: {result}", file=sys.stderr)
                return False
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  Telegram HTTP {e.code}: {body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  Telegram send failed: {e}", file=sys.stderr)
        return False


def send_telegram_text(text):
    """Plain text send (for summaries/errors)."""
    if DRY_RUN or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("---")
        print(text)
        return True
    endpoint = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as e:
        print(f"  Telegram text send failed: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Daily status — once per day, heartbeat message to confirm the cron is alive
# ---------------------------------------------------------------------------
# Fires on the first run of each UTC day (unless one has already been sent
# today). At daily cadence every run is this "first run of the day", so the
# status fires on every scheduled invocation; if the cron is ever bumped back
# to hourly, this still guarantees exactly one per day.
NEXT_RUN_DESCRIPTION = "mañana ~12:07 Madrid"


def should_send_daily_status(state):
    today_utc = time.strftime("%Y-%m-%d", time.gmtime())
    return state.get("last_daily_status_date") != today_utc


def build_daily_status(total_scraped, privates_count, ratio_pct, lifetime_tracked, new_yesterday):
    today = time.strftime("%d/%m/%Y", time.gmtime())
    now = time.strftime("%H:%M", time.gmtime())
    return (
        f"🏠 <b>Idealista Daily Status — {today}</b>\n\n"
        f"✅ Cron alive\n"
        f"📊 Última corrida: {now} UTC\n"
        f"🔍 Scrapeados: {total_scraped} · Particulares: {privates_count} ({ratio_pct}%)\n"
        f"📦 Lifetime tracked: {lifetime_tracked} listings\n"
        f"🆕 Ayer: {new_yesterday} pisos nuevos notificados\n"
        f"⏰ Próximo run: {NEXT_RUN_DESCRIPTION}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    items = run_apify_actor()

    total = len(items)
    privates = filter_private(items)
    ratio = len(privates) * 100 // max(total, 1)
    print(f"\nStats: {total} total · {len(privates)} private ({ratio}%)")

    state, bootstrap = load_state()
    seen = set(state["seen_ids"])
    new_listings = [
        item for item in privates if str(item.get("adid")) not in seen
    ]
    print(f"  Seen IDs on file: {len(seen)} · New private listings: {len(new_listings)}")

    today_utc = time.strftime("%Y-%m-%d", time.gmtime())

    if bootstrap:
        print("\n[bootstrap] First run — recording seen IDs without sending individual listings.")
        summary = (
            f"🤖 <b>Idealista monitor initialized</b>\n"
            f"Tracking {len(privates)} current private listings.\n"
            f"Next runs will only notify you about NEW ones.\n"
            f"You will receive a daily status each morning (~11:13 Madrid time)."
        )
        send_telegram_text(summary)
        for item in privates:
            seen.add(str(item.get("adid")))
        state["seen_ids"] = list(seen)
        state["last_daily_status_date"] = today_utc
        state["new_count_today"] = 0
        state["new_count_yesterday"] = 0
        save_state(state)
        print("Done (bootstrap).")
        return

    # Daily status check — before processing new listings, so the "Ayer" count
    # reflects the old state.new_count_today (yesterday's work) BEFORE rollover.
    if should_send_daily_status(state):
        print("\n[daily status] First run of the day past 9 UTC — sending heartbeat.")
        yesterday_count = state.get("new_count_today", 0)
        status_msg = build_daily_status(
            total_scraped=total,
            privates_count=len(privates),
            ratio_pct=ratio,
            lifetime_tracked=len(seen),
            new_yesterday=yesterday_count,
        )
        ok = send_telegram_text(status_msg)
        if ok:
            state["new_count_yesterday"] = yesterday_count
            state["new_count_today"] = 0
            state["last_daily_status_date"] = today_utc
        else:
            print("  WARN: daily status send failed — will retry next run.")

    if not new_listings:
        print("\nNo new private listings to notify.")
        # Still persist state (daily status rollover + updated_at)
        state["seen_ids"] = list(seen)
        save_state(state)
        return

    print(f"\nSending {len(new_listings)} new listings to Telegram...")
    sent = 0
    for item in new_listings:
        caption = format_listing(item)
        photo = get_thumbnail(item)
        ok = send_telegram_photo(photo, caption)
        if ok:
            seen.add(str(item.get("adid")))
            sent += 1
        else:
            print(f"  Skipping state update for adid={item.get('adid')} due to send failure")
        time.sleep(0.4)  # soft rate limit

    state["seen_ids"] = list(seen)
    state["new_count_today"] = state.get("new_count_today", 0) + sent
    save_state(state)
    print(f"\nDone. Sent {sent}/{len(new_listings)} listings (today total: {state['new_count_today']}).")


if __name__ == "__main__":
    main()
