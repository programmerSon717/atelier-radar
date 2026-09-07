"""월간 SPACE 채용 게시판의 과거 공고를 긁어 아카이브에 쌓는다.

과거 공고는 "누가 언제 뽑았나" 를 보려는 것이지 JD 전문이 필요한 게 아니다.
그래서 LLM 을 쓰지 않고 목록에서 직접 파싱한다 — 수백 건에 API 를 쓸 이유가 없다.
'작년 이맘때 어디가 공채를 냈는지' 를 알면 올해 준비 시점을 잡을 수 있다.

    ./.venv/bin/python tools/backfill_archive.py --pages 80
"""
import argparse
import asyncio
import base64
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin

import httpx2 as httpx
from selectolax.parser import HTMLParser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.store import DB_PATH, connect  # noqa: E402
from src.watch import UA                # noqa: E402

# 목록 페이지는 JS 로 그리고 페이지네이션도 안 먹는다. 그런데 상세 주소의 base_seq 가
# 그냥 숫자의 base64 라서(MTM2MTk= → 13619), id 를 거슬러 올라가면 과거 공고를 다 볼 수 있다.
VIEW = "https://vmspace.com/job/job_view.html?base_seq={seq}"
DATE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")
BOILER = re.compile(r"VMSPACE는 국내 최고의 건축 포털")

SCHEMA = """
CREATE TABLE IF NOT EXISTS archive (
    url        TEXT PRIMARY KEY,
    country    TEXT,
    company    TEXT,
    title      TEXT,
    posted_at  TEXT,
    deadline   TEXT,
    source     TEXT
);
"""

# 설계 관련 공고만 남긴다. 시공·자재·영업은 아카이브에도 넣을 이유가 없다.
KEEP = re.compile(r"건축|설계|디자인|인테리어|architect|design", re.I)


def seq(n: int) -> str:
    return base64.b64encode(str(n).encode()).decode()


# 상세 페이지 상단은 항상 네비게이션이고, 그 뒤에 회사명 → 제목 순으로 온다.
NAV = {"Login", "회원가입", "Facebook 로그인", "Twitter 로그인", "Naver 로그인",
       "SPACE 소개", "공지사항", "기사문의", "광고문의", "Contact",
       "menu", "search", "KOR", "ENG"}


def parse_view(html: str, url: str) -> dict | None:
    """상세 페이지에서 회사·제목·게시일·마감일을 뽑는다. LLM 은 쓰지 않는다 —
    과거 공고는 '누가 언제 뽑았나' 만 알면 되고, 수백 건에 API 를 쓸 이유가 없다."""
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript, header, footer, nav"):
        tag.decompose()
    body = tree.body or tree.root
    if body is None:
        return None

    lines = [" ".join(x.split()) for x in body.text(separator="\n").split("\n")]
    lines = [x for x in lines if x and x not in NAV and not BOILER.match(x)]
    if len(lines) < 2:
        return None

    company, title = lines[0][:120], lines[1][:200]
    # 회사명이 없고 제목부터 시작하는 경우가 있다 — 길이로 가른다
    if len(company) > 60 and len(lines) > 2:
        company, title = "(미상)", lines[0][:200]

    text = " ".join(lines[:60])
    dates = DATE.findall(text)
    fmt = lambda t: f"{t[0]}-{int(t[1]):02d}-{int(t[2]):02d}"
    posted = fmt(dates[0]) if dates else None
    deadline = fmt(dates[1]) if len(dates) > 1 else None
    if posted and deadline and deadline < posted:
        posted, deadline = deadline, posted

    return {"url": url, "company": company, "title": title,
            "posted_at": posted, "deadline": deadline}


async def crawl_ids(newest: int, count: int, concurrency: int = 2) -> list[dict]:
    """newest 부터 count 개만큼 id 를 거슬러 올라가며 상세를 읽는다."""
    sem = asyncio.Semaphore(concurrency)
    out: list[dict] = []

    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=20,
                                 follow_redirects=True) as c:
        async def one(n: int):
            url = VIEW.format(seq=seq(n))
            # 대량으로 두드리면 서버가 끊는다. 조용히 버리지 말고 몇 번 다시 시도한다 —
            # 실패를 삼키면 '수집됐다' 고 착각한 채 절반이 비게 된다.
            async with sem:
                for attempt in range(3):
                    try:
                        r = await c.get(url)
                        if r.status_code == 404:
                            return None
                        if r.status_code >= 400:
                            await asyncio.sleep(1.5 * (attempt + 1))
                            continue
                        return parse_view(r.text, url)
                    except Exception:
                        await asyncio.sleep(1.5 * (attempt + 1))
                return None

        ids = list(range(newest, newest - count, -1))
        for i in range(0, len(ids), 60):
            chunk = ids[i:i + 60]
            results = await asyncio.gather(*(one(n) for n in chunk))
            miss = sum(1 for r in results if r is None)
            for item in results:
                if item and KEEP.search(item["title"] + " " + (item["company"] or "")):
                    out.append(item)
            print(f"  … id {chunk[-1]} 까지 {len(out)}건 (이번 묶음 실패 {miss}/{len(chunk)})",
                  file=sys.stderr)
            await asyncio.sleep(1.5)   # 서버에 숨 돌릴 틈을 준다
    return out


def save(items: list[dict]) -> tuple[int, dict]:
    conn = connect()
    conn.executescript(SCHEMA)
    new = 0
    years: dict[str, int] = {}
    for it in items:
        y = (it.get("posted_at") or "")[:4]
        if y:
            years[y] = years.get(y, 0) + 1
        cur = conn.execute(
            "INSERT OR IGNORE INTO archive"
            " (url, country, company, title, posted_at, deadline, source)"
            " VALUES (?,?,?,?,?,?,?)",
            (it["url"], "KR", it["company"], it["title"],
             it.get("posted_at"), it.get("deadline"), "vmspace"),
        )
        new += cur.rowcount
    conn.commit()
    conn.close()
    return new, years


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--newest", type=int, default=13620, help="가장 최근 공고 id")
    ap.add_argument("--count", type=int, default=600, help="거슬러 올라갈 개수")
    ap.add_argument("--concurrency", type=int, default=2, help="동시 요청 수")
    args = ap.parse_args()
    items = await crawl_ids(args.newest, args.count, args.concurrency)
    new, years = save(items)
    print(f"수집 {len(items)}건 / 신규 {new}건 저장")
    for y in sorted(years, reverse=True):
        print(f"  {y}: {years[y]}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
