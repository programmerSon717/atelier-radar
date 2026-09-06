#!/usr/bin/env bash
# .env 값을 GitHub 시크릿으로 올린다. gh CLI 로그인이 되어 있어야 한다.
#   bash tools/set_secrets.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env 가 없습니다"; exit 1; }
while IFS='=' read -r k v; do
  case "$k" in
    ''|\#*) continue ;;
    GEMINI_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_IDS|TELEGRAM_TOPIC_*)
      printf '%s' "$v" | gh secret set "$k"
      echo "  ✔ $k" ;;
  esac
done < .env
echo "완료. Actions → atelier-radar 에서 확인하세요."
