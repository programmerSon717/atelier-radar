"""후보 채용 URL 을 대량으로 찔러보고 쓸만한지 판정한다.
LLM 을 쓰지 않으므로 공짜다. 채용 관련 단어가 실제로 본문에 있는지까지 본다.

    ./.venv/bin/python tools/probe_urls.py candidates.txt
    (한 줄에 "office_id<TAB>url")
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2 as httpx
from src.watch import UA, extract_text

# 채용 페이지라면 반드시 나오는 말들
HIRING = re.compile(
    r"채용|모집|지원자격|신입|경력|採用|募集|応募|新卒|インターン|求人|"
    r"徵才|招募|職缺|應徵|實習|recruit|career|job|position|intern|apply|hiring",
    re.I,
)
# 실제 '공고'가 있을 때만 나오는 말들 (메뉴에 '채용'만 있는 페이지와 구분)
POSTING = re.compile(
    r"지원자격|자격요건|모집분야|모집기간|접수기간|우대사항|"
    r"応募資格|募集要項|募集職種|エントリー|選考|"
    r"應徵條件|工作內容|職務說明|需求人數|"
    r"qualifications|requirements|responsibilities|how to apply|deadline",
    re.I,
)


async def probe(client, oid: str, url: str):
    try:
        r = await client.get(url, follow_redirects=True)
        if r.status_code >= 400:
            return oid, url, f"HTTP {r.status_code}", 0, False, False
        t = extract_text(r.text)
        return oid, url, "OK", len(t), bool(HIRING.search(t)), bool(POSTING.search(t))
    except Exception as e:
        return oid, url, type(e).__name__, 0, False, False


async def main(path: str):
    pairs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        oid, url = line.split(None, 1)
        pairs.append((oid, url.strip()))

    sem = asyncio.Semaphore(10)
    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": UA, "Accept-Language": "ko,ja,zh-TW,en"}
    ) as client:
        async def g(p):
            async with sem:
                return await probe(client, *p)
        rows = await asyncio.gather(*(g(p) for p in pairs))

    rows.sort(key=lambda r: (not r[5], not r[4], -r[3]))
    print(f"{'office':22} {'상태':10} {'글자':>6}  채용어 공고어  URL")
    print("-" * 110)
    for oid, url, st, n, h, p in rows:
        print(f"{oid:22} {st:10} {n:6}  {'✓' if h else '·':^5} {'✓' if p else '·':^5}  {url[:60]}")
    good = [r for r in rows if r[5]]
    print(f"\n실제 공고 있어 보이는 곳: {len(good)}/{len(rows)}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
