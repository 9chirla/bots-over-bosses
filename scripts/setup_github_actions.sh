#!/usr/bin/env bash
# Push local .env + Google JSON files to GitHub Actions secrets.
# Requires: gh CLI logged in, repo pushed to GitHub.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v gh >/dev/null; then
  echo "Install GitHub CLI: brew install gh"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Run: gh auth login"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Missing .env in $ROOT"
  exit 1
fi

set_secret() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "  skip $name (empty)"
    return
  fi
  printf '%s' "$value" | gh secret set "$name"
  echo "  set $name"
}

set_secret_file_b64() {
  local name="$1"
  local path="$2"
  if [[ ! -f "$path" ]]; then
    echo "  skip $name ($path not found)"
    return
  fi
  base64 < "$path" | tr -d '\n' | gh secret set "$name"
  echo "  set $name (from $path)"
}

echo "Reading .env..."
# shellcheck disable=SC1091
source .env

echo "Uploading secrets to $(gh repo view --json nameWithOwner -q .nameWithOwner)..."

set_secret ADZUNA_APP_ID "${ADZUNA_APP_ID:-}"
set_secret ADZUNA_APP_KEY "${ADZUNA_APP_KEY:-}"
set_secret DEEPSEEK_API_KEY "${DEEPSEEK_API_KEY:-}"
set_secret TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN:-}"
set_secret TELEGRAM_CHAT_ID "${TELEGRAM_CHAT_ID:-}"
set_secret GOOGLE_DOCS_FOLDER_ID "${GOOGLE_DOCS_FOLDER_ID:-}"
set_secret GOOGLE_SHEETS_ID "${GOOGLE_SHEETS_ID:-}"

set_secret_file_b64 GOOGLE_OAUTH_TOKEN_B64 "${GOOGLE_OAUTH_TOKEN:-google_token.json}"
set_secret_file_b64 GOOGLE_OAUTH_CLIENT_SECRETS_B64 "${GOOGLE_OAUTH_CLIENT_SECRETS:-client_secret.json}"
set_secret_file_b64 GOOGLE_SERVICE_ACCOUNT_JSON_B64 "${GOOGLE_SERVICE_ACCOUNT_JSON:-service_account.json}"

echo ""
echo "Done. Enable the workflow:"
echo "  GitHub → Actions → Daily UK Job Search → Run workflow (test)"
echo "Scheduled: 06:00 UTC every day"
