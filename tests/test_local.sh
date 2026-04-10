#!/usr/bin/env bash
# Local dry-run test using a JSON file already fetched from Apify.
# Does NOT call Apify API and does NOT send Telegram messages.
#
# Usage:
#   bash tests/test_local.sh <path-to-apify-results.json>
#
# Example:
#   bash tests/test_local.sh /home/lasantoneta/.claude/tmp/idealista-apify.json

set -e

JSON_FILE="${1:-/home/lasantoneta/.claude/tmp/idealista-apify.json}"

if [[ ! -f "$JSON_FILE" ]]; then
  echo "ERROR: JSON file not found: $JSON_FILE"
  exit 1
fi

cd "$(dirname "$0")/.."

LOCAL_JSON_INPUT="$JSON_FILE" \
DRY_RUN=true \
STATE_FILE=state/seen_ids.test.json \
python3 scripts/idealista_monitor.py

echo ""
echo "---"
echo "Dry run complete."
echo "Test state file written to state/seen_ids.test.json (safe to delete)."
