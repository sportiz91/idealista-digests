# Idealista Digests

Daily monitor for private-owner (dueño directo) rental listings on Idealista, delivered to Telegram. Runs on GitHub Actions, zero-cost to host, fits comfortably in the Apify free tier.

## What it does

Once a day at ~12:07 Madrid time:
1. Calls the [`memo23/idealista-scraper`](https://apify.com/memo23/idealista-scraper) Apify actor with your saved search URL
2. Filters results to only `contactInfo.userType == "private"` (direct owners, no agencies)
3. Sends a daily status message (heartbeat + metrics) to Telegram
4. Dedupes new listings against `state/seen_ids.json` (committed back to repo)
5. Posts each new listing to Telegram as a photo with caption (price, size, rooms, contact, description, link)

Zero runtime dependencies — Python stdlib only.

## Cost

The actor charges ~$0.001 per item returned, and each run returns ~120 items (the first page of the search). Expected cost: **~$3.81/month** (1 run × 120 items × $0.001/item × 30 days), fits within the Apify free tier of $5/month.

**Note**: `monitoringMode: true` is passed in the input but empirically does not reduce billable items — the actor returns and bills for ~120 items per run regardless. If you want lower cost, lower the cron frequency; if you want higher cost for faster alerts, bump it to multiple times per day and expect to pay for overages beyond the free tier.

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
    - cron: '7 10 * * *'      # Daily at 10:07 UTC = ~12:07 Madrid (default)
    # - cron: '7 10,17 * * *' # Twice a day: ~12:07 and ~19:07 Madrid (~$7.60/mo, over free tier)
    # - cron: '7 */4 * * *'   # Every 4h (~$22/mo, needs Apify paid plan)
    # - cron: '13 * * * *'    # Every hour (~$91/mo, needs Apify paid plan)
```

If you change the cadence, also update `NEXT_RUN_DESCRIPTION` at the top of `scripts/idealista_monitor.py` so the daily status message reflects the new schedule.

Daily was chosen to stay within the Apify free tier. Private listings do move fast on Idealista, but the real trade-off is cost vs. speed — document your decision based on budget.

## Resetting state

If you want to reset dedup (e.g., after changing `SEARCH_URL` to a different zone):

```bash
rm state/seen_ids.json
git commit -am "reset: clear seen state"
git push
```

Next run will bootstrap again.
