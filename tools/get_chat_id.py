"""봇에게 아무 메시지나 보낸 뒤 이걸 실행하면 chat_id 가 나온다.
    ./.venv/bin/python tools/get_chat_id.py
"""
import os
import sys

import httpx2 as httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not token:
    sys.exit(".env 에 TELEGRAM_BOT_TOKEN 이 없습니다")

r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
data = r.json()
if not data.get("ok"):
    sys.exit(f"텔레그램 오류: {data}")

seen = {}
for u in data.get("result", []):
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat") or {}
    if chat.get("id"):
        who = chat.get("username") or chat.get("first_name") or chat.get("title") or "?"
        seen[chat["id"]] = who

if not seen:
    print("업데이트가 없습니다. 봇 채팅방에서 /start 를 누르고 아무 메시지나 보낸 뒤 다시 실행하세요.")
else:
    print("찾은 chat_id:")
    for cid, who in seen.items():
        print(f"  {cid}   ({who})")
    print("\n.env 에 이렇게 넣으세요:")
    print(f"TELEGRAM_CHAT_IDS={','.join(str(c) for c in seen)}")
