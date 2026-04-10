# Idealista Digests

Hourly monitor for private-owner (dueño directo) rental listings on Idealista, delivered to Telegram. Runs on GitHub Actions, zero-cost to host.

## What it does

Every hour:
1. Calls the [`memo23/idealista-scraper`](https://apify.com/memo23/idealista-scraper) Apify actor with your saved search URL
2. Filters results to only `contactInfo.userType == "private"` (direct owners, no agencies)
3. Dedupes against `state/seen_ids.json` (committed back to repo)
4. Posts each new listing to Telegram as a photo with caption (price, size, rooms, contact, description, link)

Zero runtime dependencies — Python stdlib only.

## Cost

With `MONITORING_MODE=true` (default) Apify only charges for new listings per run, not for re-scraping the same ones. Expected cost: **~$3-5/month**, fits in the Apify free tier ($5/mo credit).

Without monitoring mode: ~$18/month (each run re-scrapes the full first page).

## Setup

### 1. Fork or clone this repo to GitHub

You need your own copy so GitHub Actions can commit the state file back.

### 2. Configure secrets & variables

In the GitHub repo: **Settings → Secrets and variables → Actions**.

**Secrets** (encrypted, masked in logs):
- `APIFY_TOKEN` — from [console.apify.com/account/integrations](https://console.apify.com/account/integrations)
- `TELEGRAM_BOT_TOKEN` — create a bot with [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID` — your user ID (chat with [@userinfobot](https://t.me/userinfobot) to get it)
- `SEARCH_URL` — your Idealista search URL with all filters applied (stored as a Secret so the URL doesn't leak in public workflow logs)

### 3. Enable Actions

In the repo: **Actions** tab → enable workflows. The monitor runs at `:13` of every hour, plus you can trigger it manually from the Actions tab for testing.

### 4. First run (bootstrap)

On first run, the script records all currently-visible private listings as "seen" **without sending them individually to Telegram**. You only get a one-line summary: `"Tracking N private listings"`. From run #2 onwards, only brand-new listings are notified.

This avoids a spam blast of 10-50 messages on the first run.

## Local testing

Test the full pipeline (parser + filter + dedup + message formatting) locally without calling Apify or sending to Telegram:

```bash
bash tests/test_local.sh path/to/apify-results.json
```

This uses the JSON you already downloaded from an Apify run (via the console's Export button). `DRY_RUN=true` prints the formatted messages to stdout instead of sending them.

## Configuration

All configuration is via environment variables (set as secrets/variables in Actions, or in your shell for local runs):

| Variable | Default | Description |
|---|---|---|
| `APIFY_TOKEN` | (required) | Apify API token |
| `APIFY_ACTOR_ID` | `memo23~idealista-scraper` | Actor to call. Swap if memo23 ever breaks. |
| `SEARCH_URL` | (required) | Your Idealista search URL |
| `MAX_ITEMS` | `50` | Max listings per run. Lower = cheaper. |
| `MONITORING_MODE` | `true` | Only scrape new listings since last run. Big cost saver. |
| `TELEGRAM_BOT_TOKEN` | (required) | From @BotFather |
| `TELEGRAM_CHAT_ID` | (required) | Your Telegram user ID |
| `STATE_FILE` | `state/seen_ids.json` | Dedup state path |
| `DRY_RUN` | `false` | Print to stdout instead of sending to Telegram |
| `LOCAL_JSON_INPUT` | (empty) | If set, read listings from local JSON file instead of calling Apify |

## Changing the cron frequency

Edit `.github/workflows/idealista-monitor.yml`:

```yaml
on:
  schedule:
    - cron: '13 * * * *'      # Every hour (default)
    # - cron: '13 */2 * * *'  # Every 2 hours
    # - cron: '13 */4 * * *'  # Every 4 hours
```

Hourly is recommended for private listings — they disappear fast.

## Resetting state

If you want to reset dedup (e.g., after changing `SEARCH_URL` to a different zone):

```bash
rm state/seen_ids.json
git commit -am "reset: clear seen state"
git push
```

Next run will bootstrap again.
