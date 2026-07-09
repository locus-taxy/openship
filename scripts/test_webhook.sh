#!/usr/bin/env bash
#
# Fire sample Confluence + Jira webhook payloads at a running backend to verify the
# freshness endpoints (auth + dispatch + background reindex) without needing Atlassian
# to actually send anything. Use this for a quick local check before wiring up real
# webhooks (which need admin access to register in Atlassian).
#
# Usage:
#   scripts/test_webhook.sh [BASE_URL]
#
# BASE_URL defaults to http://localhost:3005 (the backend port). Point it at a tunnel
# (https://xxxx.trycloudflare.com) to test the public path too. Note: NO "/py" prefix —
# that's only the frontend dev proxy; the backend serves /webhooks/... directly.
#
# Config (env vars or edit the defaults below):
#   JIRA_WEBHOOK_SECRET / CONFLUENCE_WEBHOOK_SECRET  (required; auto-loaded from .env)
#   JIRA_KEY        a real ingested issue key      (e.g. AR-2847)
#   CONF_PAGE_ID    a real ingested Confluence id  (e.g. 5726208068)
#   SITE_URL        your Atlassian site            (e.g. https://acme.atlassian.net)
#   CLOUD_ID        your connection cloud id
#
set -euo pipefail

BASE_URL="${1:-http://localhost:3005}"

# Load webhook secrets from .env if not already in the environment.
ENV_FILE="$(dirname "$0")/../.env"
if [[ -f "$ENV_FILE" ]]; then
  [[ -z "${JIRA_WEBHOOK_SECRET:-}" ]] && JIRA_WEBHOOK_SECRET="$(grep -E '^JIRA_WEBHOOK_SECRET=' "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
  [[ -z "${CONFLUENCE_WEBHOOK_SECRET:-}" ]] && CONFLUENCE_WEBHOOK_SECRET="$(grep -E '^CONFLUENCE_WEBHOOK_SECRET=' "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
fi

JIRA_WEBHOOK_SECRET="${JIRA_WEBHOOK_SECRET:-}"
CONFLUENCE_WEBHOOK_SECRET="${CONFLUENCE_WEBHOOK_SECRET:-}"
JIRA_KEY="${JIRA_KEY:-AR-1}"
CONF_PAGE_ID="${CONF_PAGE_ID:-123456}"
SITE_URL="${SITE_URL:-https://your-site.atlassian.net}"
CLOUD_ID="${CLOUD_ID:-your-cloud-id}"

post() {  # post <label> <url> <json> ; prints the HTTP status
  local label="$1" url="$2" body="$3" code
  code="$(curl -s -o /tmp/_wh_body.$$ -w '%{http_code}' -X POST "$url" \
    -H 'Content-Type: application/json' -d "$body" || echo "000")"
  printf '  %-42s -> %s  %s\n' "$label" "$code" "$(cat /tmp/_wh_body.$$ 2>/dev/null)"
  rm -f "/tmp/_wh_body.$$"
}

echo "Target: $BASE_URL"

echo "== Auth (expect 401) =="
post "jira wrong secret" \
  "$BASE_URL/webhooks/jira?secret=WRONG" \
  '{"webhookEvent":"jira:issue_updated","issue":{"key":"'"$JIRA_KEY"'"}}'

echo "== Jira (expect 200 accepted) =="
if [[ -n "$JIRA_WEBHOOK_SECRET" ]]; then
  post "jira issue_updated ($JIRA_KEY)" \
    "$BASE_URL/webhooks/jira?secret=$JIRA_WEBHOOK_SECRET" \
    '{"webhookEvent":"jira:issue_updated","issue":{"key":"'"$JIRA_KEY"'","self":"'"$SITE_URL"'/rest/api/2/issue/1"}}'
else
  echo "  (skipped — set JIRA_WEBHOOK_SECRET)"
fi

echo "== Confluence (expect 200 accepted) =="
if [[ -n "$CONFLUENCE_WEBHOOK_SECRET" ]]; then
  post "confluence page_updated ($CONF_PAGE_ID)" \
    "$BASE_URL/webhooks/confluence?secret=$CONFLUENCE_WEBHOOK_SECRET" \
    '{"event":"page_updated","page":{"id":"'"$CONF_PAGE_ID"'"},"cloudId":"'"$CLOUD_ID"'"}'
else
  echo "  (skipped — set CONFLUENCE_WEBHOOK_SECRET)"
fi

echo
echo "Valid calls return {\"status\":\"accepted\"} immediately; the fetch+reindex runs in the"
echo "background. Confirm it worked by checking document_pages.last_synced_at for the item,"
echo "or by asking the knowledge chat about it. (Use real JIRA_KEY / CONF_PAGE_ID / SITE_URL /"
echo "CLOUD_ID so the background reindex actually resolves the tenant and fetches the item.)"
