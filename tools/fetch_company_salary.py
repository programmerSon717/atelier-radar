"""회사별 연봉을 실제 출처에서 가져온다.

업계 평균은 쓰지 않는다(사용자 지시). 대신 **그 회사** 값만 싣는다.
사람인 기업정보는 국민연금 신고액 기반 평균연봉을 공개한다 — 로그인 없이 볼 수 있고
출처를 링크할 수 있다. 다만 **전 직원 평균**이지 신입 초봉이 아니다. 그래서 화면에도
"회사 전체 평균" 이라고 못 박는다. 신입 초봉은 여기서 알 수 없다.

    ./.venv/bin/python tools/fetch_company_salary.py            # 저장된 공고의 회사들
    ./.venv/bin/python tools/fetch_company_salary.py 희림 정림    # 이름 직접 지정

결과는 data/salary_company.yaml 에 쌓인다 (저장소에 넣어 클라우드도 같이 쓴다).
"""
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml
from selectolax.parser import HTMLParser

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "salary_company.yaml"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/128.0 Safari/537.36"}
SEARCH = "https://www.saramin.co.kr/zf_user/search/company?searchword={}"

CORP = re.compile(r"\(주\)|㈜|주식회사|\(유\)|유한회사")
# 사람인 검색은 긴 정식명칭으로는 잘 안 걸린다. 핵심 이름만 남겨 검색한다.
SUFFIX = re.compile(r"종합건축사사무소|건축사\s*사무소|건축사사무소|엔지니어링종합건축사사무소|"
                    r"엔지니어링|건축설계사무소|디자인그룹|아키텍츠?|건축$")
MONEY = re.compile(r"평균연봉\s*([\d,]+)\s*만원")
# 이름이 비슷한 남의 회사를 물어오면 안 된다. 실제로 "희림" 을 찾다가 포장 공사업체를,
# "삼우" 를 찾다가 레미콘 제조업체를 잡았다. 업종까지 맞아야 그 회사로 인정한다.
ARCH_BIZ = re.compile(r"건축\s*설계|건축설계|엔지니어링\s*서비스|건축기술|기술\s*서비스|"
                      r"도시\s*계획|인테리어|실내\s*건축|조경\s*설계|건설\s*기술")


def norm(s: str) -> str:
    return re.sub(r"[\s·,.\-_()（）]", "", CORP.sub("", s or "")).lower()


def core_of(name: str) -> str:
    c = SUFFIX.sub("", CORP.sub("", name or "")).strip()
    return c or name


def lookup(name: str, client: httpx.Client) -> dict | None:
    """사람인 기업검색에서 이름이 맞는 회사의 평균연봉을 찾는다."""
    q = core_of(name)
    url = SEARCH.format(quote(q))
    r = client.get(url, timeout=20, follow_redirects=True)
    if r.status_code >= 400:
        return None
    tree = HTMLParser(r.text)
    target, short = norm(name), norm(core_of(name))
    for card in tree.css("div, li"):
        txt = " ".join((card.text() or "").split())
        if "평균연봉" not in txt or len(txt) > 900:
            continue
        # 카드 안에 회사 이름이 들어 있어야 그 회사 값이다
        link = card.css_first("a")
        label = " ".join((link.text() or "").split()) if link else ""
        if not label:
            continue
        lab = norm(label)
        if not (lab == target or target in lab or lab in target
                or (len(short) >= 2 and short in lab)):
            continue
        m = MONEY.search(txt)
        if not m:
            continue
        biz = re.search(r"업종\s*([^\s].{0,30}?)\s*(?:재무정보|기업주소|평균연봉)", txt)
        industry = biz.group(1) if biz else ""
        # 이름만 비슷한 다른 업종 회사는 버린다 (정식명칭이 정확히 같을 때만 예외)
        if lab != target and not ARCH_BIZ.search(industry):
            continue
        return {
            "company": label,
            "average": f"{m.group(1)}만원",
            "basis": "회사 전체 평균 (국민연금 신고액 기반) — 신입 초봉이 아니다",
            "industry": industry or None,
            "source": "사람인 기업정보",
            "source_url": url,
            "checked_at": date.today().isoformat(),
        }
    return None


def target_names() -> list[str]:
    db = ROOT / "store" / "radar.sqlite"
    names: list[str] = []
    if db.exists():
        with sqlite3.connect(db) as c:
            for (pl,) in c.execute("SELECT payload FROM sent_posting"):
                d = json.loads(pl)
                if d.get("company"):
                    names.append(d["company"])
    for f in (ROOT / "data" / "targets").glob("korea.yaml"):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for o in doc.get("offices") or []:
            if o.get("tier") == "job_board":
                continue
            n = (o.get("name") or {}).get("ko")
            if n:
                names.append(n)
    seen, out = set(), []
    for n in names:
        k = norm(n)
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def main() -> int:
    names = sys.argv[1:] or target_names()
    doc = yaml.safe_load(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    doc = doc or {}
    table = doc.setdefault("companies", {})

    with httpx.Client(headers=UA) as client:
        for n in names:
            key = norm(n)
            try:
                hit = lookup(n, client)
            except Exception as e:
                print(f"  ? {n[:24]:26} {type(e).__name__}")
                continue
            if hit:
                table[key] = hit
                print(f"  ✓ {n[:24]:26} {hit['average']:>10}  ({hit.get('industry') or ''})")
            else:
                print(f"  – {n[:24]:26} 없음")

    OUT.write_text(
        "# 회사별 연봉 — tools/fetch_company_salary.py 가 채운다. 손으로 고치지 말 것.\n"
        "# 사람인 기업정보(국민연금 신고액 기반) 의 **회사 전체 평균**이다. 신입 초봉이 아니다.\n"
        + yaml.safe_dump(doc, allow_unicode=True, sort_keys=True),
        encoding="utf-8")
    print(f"\n{len(table)}곳 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
