"""텔레그램 발송. 실패해도 파이프라인을 죽이지 않는다.

그룹이 포럼(토픽)이면 국가별 토픽으로 나눠 보낸다.
토픽 id 는 .env 의 TELEGRAM_TOPIC_KR / _JP / _TW 로 준다.
"""
import asyncio
import os

import httpx2 as httpx

API = "https://api.telegram.org/bot{token}/{method}"


def chat_ids() -> list[str]:
    raw = os.environ.get("TELEGRAM_CHAT_IDS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def topic_id(country: str) -> int | None:
    """국가 코드 → 토픽 id. 설정이 없으면 None (일반 채팅으로 간다)."""
    raw = os.environ.get(f"TELEGRAM_TOPIC_{country.upper()}")
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


async def send(text: str, country: str | None = None, disable_preview: bool = True) -> list[str]:
    """실패한 chat_id 들을 돌려준다. country 를 주면 그 나라 토픽으로 보낸다."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return ["TELEGRAM_BOT_TOKEN 없음"]
    targets = chat_ids()
    if not targets:
        return ["TELEGRAM_CHAT_IDS 없음"]

    thread = topic_id(country) if country else None
    failed: list[str] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for cid in targets:
            payload = {
                "chat_id": cid,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
            }
            if thread is not None:
                payload["message_thread_id"] = thread
            try:
                r = await client.post(API.format(token=token, method="sendMessage"), json=payload)
                if r.status_code != 200:
                    failed.append(f"{cid}: {r.status_code} {r.text[:120]}")
                await asyncio.sleep(0.4)  # 텔레그램 초당 제한 회피
            except Exception as e:
                failed.append(f"{cid}: {type(e).__name__}")
    return failed
