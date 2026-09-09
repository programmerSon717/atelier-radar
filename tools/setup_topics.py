"""그룹에 토픽을 만들고 .env 에 id 를 적어준다.
봇에게 '토픽 관리(Manage Topics)' 권한이 있어야 한다.

    ./.venv/bin/python tools/setup_topics.py            # 없는 것만 만든다
    ./.venv/bin/python tools/setup_topics.py --rename   # 이미 있는 토픽 이름을 고친다

토픽 이름도 봇 언어(번체중문)로 맞춘다 — 메시지는 중문인데 토픽만 한국어면 어색하다.
OPEN 은 '지금 바로 넣을 수 있는 것' 만 모으는 자리다. 나라별 토픽에도 그대로 가고,
여기에 한 번 더 온다 (src/notify.py: send_ok).
"""
import os
import sys
from pathlib import Path

import httpx2 as httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = (os.environ.get("TELEGRAM_CHAT_IDS") or "").split(",")[0].strip()
if not TOKEN or not CHAT:
    sys.exit(".env 에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS 가 필요합니다")

cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}
LANG = (cfg.get("telegram") or {}).get("locale", "zh_TW")
W = (yaml.safe_load((ROOT / "config" / "locales" / f"{LANG}.yaml").read_text(encoding="utf-8"))
     or {}).get("web", {})

# 이름은 사이트 문구를 그대로 쓴다 (config/locales/*.yaml → site/ui.js 와 같은 값)
TOPICS = [
    ("OPEN", f"✅ {W.get('g_open', 'Open to apply')}", 0x6FB9F0),
    ("KR", W.get("kr", "🇰🇷"), 0x6FB9F0),
    ("JP", W.get("jp", "🇯🇵"), 0xFFD67E),
    ("TW", W.get("tw", "🇹🇼"), 0xCB86DB),
]
API = f"https://api.telegram.org/bot{TOKEN}/"
RENAME = "--rename" in sys.argv


def die_if_no_rights(desc: str) -> None:
    if "not enough rights" in desc.lower() or "CHAT_ADMIN_REQUIRED" in desc:
        sys.exit("봇에게 '토픽 관리(Manage Topics)' 권한이 없습니다.\n"
                 "그룹 → 관리자 → 봇 → 'Manage Topics' 켜고 다시 실행하세요.")


info = httpx.get(API + "getChat", params={"chat_id": CHAT}, timeout=20).json().get("result", {})
if not info.get("is_forum"):
    sys.exit("이 그룹은 포럼(토픽)이 아닙니다. 그룹 설정에서 '토픽'을 켜주세요.")

lines = []
for code, name, color in TOPICS:
    have = os.environ.get(f"TELEGRAM_TOPIC_{code}")
    if have and RENAME:
        r = httpx.post(API + "editForumTopic",
                       json={"chat_id": CHAT, "message_thread_id": int(have), "name": name},
                       timeout=20).json()
        die_if_no_rights(r.get("description", ""))
        print(f"  {name}: {'이름 바꿈' if r.get('ok') else '실패 — ' + r.get('description', '')} (id={have})")
        continue
    if have:
        print(f"  {name}: 이미 있음 (id={have}) — 이름을 고치려면 --rename")
        continue
    r = httpx.post(API + "createForumTopic",
                   json={"chat_id": CHAT, "name": name, "icon_color": color}, timeout=20).json()
    if not r.get("ok"):
        die_if_no_rights(r.get("description", ""))
        print(f"  {name}: 실패 — {r.get('description', '')}")
        continue
    tid = r["result"]["message_thread_id"]
    print(f"  {name}: 생성됨 (id={tid})")
    lines.append(f"TELEGRAM_TOPIC_{code}={tid}")

if lines:
    with open(ROOT / ".env", "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(lines) + "\n")
    print("\n.env 에 추가했습니다 (GitHub Actions 시크릿에도 넣어야 클라우드에서 돕니다):")
    print("\n".join(lines))
