"""그룹에 한국/일본/대만 토픽을 만들고 .env 에 id 를 적어준다.
봇에게 '토픽 관리(Manage Topics)' 권한이 있어야 한다.

    ./.venv/bin/python tools/setup_topics.py
"""
import os
import sys
from pathlib import Path

import httpx2 as httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = (os.environ.get("TELEGRAM_CHAT_IDS") or "").split(",")[0].strip()
if not TOKEN or not CHAT:
    sys.exit(".env 에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS 가 필요합니다")

TOPICS = [("KR", "🇰🇷 한국", 0x6FB9F0), ("JP", "🇯🇵 일본", 0xFFD67E), ("TW", "🇹🇼 대만", 0xCB86DB)]
API = f"https://api.telegram.org/bot{TOKEN}/"

info = httpx.get(API + "getChat", params={"chat_id": CHAT}, timeout=20).json().get("result", {})
if not info.get("is_forum"):
    sys.exit("이 그룹은 포럼(토픽)이 아닙니다. 그룹 설정에서 '토픽'을 켜주세요.")

lines = []
for code, name, color in TOPICS:
    r = httpx.post(API + "createForumTopic",
                   json={"chat_id": CHAT, "name": name, "icon_color": color}, timeout=20).json()
    if not r.get("ok"):
        desc = r.get("description", "")
        if "not enough rights" in desc.lower() or "CHAT_ADMIN_REQUIRED" in desc:
            sys.exit("봇에게 '토픽 관리(Manage Topics)' 권한이 없습니다.\n"
                     "그룹 → 관리자 → 봇 → 'Manage Topics' 켜고 다시 실행하세요.")
        print(f"  {name}: 실패 — {desc}")
        continue
    tid = r["result"]["message_thread_id"]
    print(f"  {name}: 생성됨 (id={tid})")
    lines.append(f"TELEGRAM_TOPIC_{code}={tid}")

if lines:
    with open(ROOT / ".env", "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines) + "\n")
    print("\n.env 에 추가했습니다:")
    print("\n".join(lines))
