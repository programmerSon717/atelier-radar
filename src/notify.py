"""텔레그램 발송. 실패해도 파이프라인을 죽이지 않는다.

그룹이 포럼(토픽)이면 국가별 토픽으로 나눠 보낸다.
토픽 id 는 .env 의 TELEGRAM_TOPIC_KR / _JP / _TW 로 준다.
바로 지원할 수 있는 공고(gate=open)는 TELEGRAM_TOPIC_OPEN 토픽에도 같이 보낸다 —
'지금 넣을 수 있는 것' 만 모아 보는 자리가 따로 있어야 나라별 목록에 묻히지 않는다.

텔레그램 한 통은 4096자까지다. 웹은 길이 제한이 없으므로, 웹과 같은 내용을 그대로
실으면 넘치는 공고가 나온다. 잘라내지 않고 **여러 통으로 나눠** 보낸다.
"""
import asyncio
import os
from functools import lru_cache
from pathlib import Path

import httpx2 as httpx
import yaml

API = "https://api.telegram.org/bot{token}/{method}"

# 4096 이 한계다. 태그가 잘리지 않게 여유를 둔다.
LIMIT = 3800


def chat_ids() -> list[str]:
    raw = os.environ.get("TELEGRAM_CHAT_IDS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


@lru_cache(maxsize=1)
def _configured_topics() -> dict:
    """config/settings.yaml 의 telegram.topics — 시크릿을 빠뜨렸을 때의 바닥값."""
    try:
        cfg = yaml.safe_load(
            (Path(__file__).resolve().parent.parent / "config" / "settings.yaml")
            .read_text(encoding="utf-8")) or {}
        return (cfg.get("telegram") or {}).get("topics") or {}
    except Exception:
        return {}


def topic_id(name: str) -> int | None:
    """국가 코드(또는 OPEN) → 토픽 id. 없으면 None (일반 채팅으로 간다).

    환경변수가 먼저다. 없으면 settings.yaml 에 적어 둔 값을 쓴다 — 시크릿을 하나
    빠뜨렸다고 그 토픽 글이 조용히 일반 채팅으로 새면 알아채기 어렵다."""
    raw = os.environ.get(f"TELEGRAM_TOPIC_{name.upper()}")
    if raw in (None, ""):
        raw = _configured_topics().get(name.upper())
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _split_block(block: str, limit: int) -> list[str]:
    """한 덩어리가 혼자 한계를 넘을 때. 인용구는 태그를 다시 열어 준다."""
    quoted = block.startswith("<blockquote") and block.endswith("</blockquote>")
    if quoted:
        open_tag = block[:block.index(">") + 1]
        body = block[len(open_tag):-len("</blockquote>")]
        wrap = lambda s: f"{open_tag}{s}</blockquote>"        # noqa: E731
        room = limit - len(open_tag) - len("</blockquote>")
    else:
        body, wrap, room = block, (lambda s: s), limit

    out, cur = [], ""
    for line in body.split("\n"):
        line = line[:room]                    # 한 줄이 혼자 넘치면 그 줄만 자른다
        piece = line if not cur else cur + "\n" + line
        if len(piece) <= room:
            cur = piece
        else:
            out.append(wrap(cur))
            cur = line
    if cur:
        out.append(wrap(cur))
    return out


def chunks(text: str, limit: int = LIMIT) -> list[str]:
    """빈 줄로 나뉜 덩어리 단위로 묶는다 — 태그 한가운데서 끊기지 않게."""
    parts: list[str] = []
    cur = ""
    for block in text.split("\n\n"):
        piece = block if not cur else cur + "\n\n" + block
        if len(piece) <= limit:
            cur = piece
            continue
        if cur:
            parts.append(cur)
            cur = ""
        if len(block) <= limit:
            cur = block
        else:
            parts.extend(_split_block(block, limit))
    if cur:
        parts.append(cur)
    return parts or [text]


async def _post(client, token: str, cid: str, text: str, thread: int | None,
                disable_preview: bool) -> str | None:
    payload = {
        "chat_id": cid,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if thread is not None:
        payload["message_thread_id"] = thread
    r = await client.post(API.format(token=token, method="sendMessage"), json=payload)
    await asyncio.sleep(0.4)   # 텔레그램 초당 제한 회피
    return None if r.status_code == 200 else f"{r.status_code} {r.text[:160]}"


async def send(text: str, country: str | None = None, disable_preview: bool = True,
               topic: str | None = None, part_fmt: str | None = None) -> list[str]:
    """실패한 chat_id 들을 돌려준다. country(또는 topic)를 주면 그 토픽으로 보낸다.

    한 곳이라도 성공하면 호출부는 '보냈다'로 처리한다 (send_ok 참조) —
    안 그러면 성공한 챗에 다음 실행 때 같은 공고가 또 간다."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return ["TELEGRAM_BOT_TOKEN 없음"]
    targets = chat_ids()
    if not targets:
        return ["TELEGRAM_CHAT_IDS 없음"]

    thread = topic_id(topic or country) if (topic or country) else None
    pieces = chunks(text)
    if len(pieces) > 1 and part_fmt:
        n = len(pieces)
        pieces = [p + "\n\n<i>" + part_fmt.replace("{i}", str(i + 1)).replace("{n}", str(n)) + "</i>"
                  for i, p in enumerate(pieces)]

    failed: list[str] = []
    async with httpx.AsyncClient(timeout=20) as client:
        for cid in targets:
            for piece in pieces:
                try:
                    err = await _post(client, token, cid, piece, thread, disable_preview)
                    if err:
                        failed.append(f"{cid}: {err}")
                        break        # 앞이 실패했는데 뒤를 이어 보내면 조각만 남는다
                except Exception as e:
                    failed.append(f"{cid}: {type(e).__name__}")
                    break
    return failed


async def send_ok(text: str, country: str | None = None, gate: str | None = None,
                  part_fmt: str | None = None) -> tuple[bool, list[str]]:
    """(하나라도 갔는가, 실패 목록). 부분 실패로 인한 중복 발송을 막는다.

    gate 가 'open' 이면 '바로 지원 가능' 토픽에도 같이 보낸다. 그쪽 실패는
    '못 보냈다'로 치지 않는다 — 나라 토픽에 갔으면 사람은 이미 봤다."""
    targets = chat_ids()
    failed = await send(text, country=country, part_fmt=part_fmt)
    delivered = bool(targets) and len(failed) < len(targets)
    if gate == "open" and topic_id("OPEN") is not None:
        failed += await send(text, topic="OPEN", part_fmt=part_fmt)
    return delivered, failed
