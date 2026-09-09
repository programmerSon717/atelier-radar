"""사이트가 읽을 data.json 을 만든다.

HTML 에 데이터를 구워 넣지 않고 분리한다. 그래야 페이지를 다시 만들지 않아도
데이터만 갈아끼우면 화면이 갱신되고, 브라우저에서 필터·정렬을 그때그때 할 수 있다.
"""
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import eligibility, relevance, salary, verified                      # noqa: E402
from src.match import assess, is_new_grad_ok
from src.scope import country_of                     # noqa: E402
from src.models import Posting                   # noqa: E402
from src.targets import load_offices             # noqa: E402


# ── 공개 사이트로 나가는 것에서 신원을 지운다 ───────────────────
# 메일 초안 서명에 본인 이름이, 본문에 학교 이름이 들어간다. docs/ 는 GitHub Pages 로
# 그대로 공개되므로 여기서 반드시 가린다. 텔레그램(비공개 그룹)에는 실명 그대로 나간다.
def _identity_known() -> bool:
    """가릴 대상을 알고 있는가. 모르면 메일 초안을 아예 싣지 않는다 (실패-차단)."""
    return bool(os.environ.get("CANDIDATE_NAME"))


def _redact(v):
    if isinstance(v, str):
        # 화면에서 언어에 맞게 바꿔 끼우려고 중립 토큰으로 가린다 (app.js 가 치환한다)
        for env, mask in (("CANDIDATE_NAME", "[NAME]"),
                          ("CANDIDATE_SCHOOL", "[SCHOOL]")):
            real = os.environ.get(env)
            if real:
                v = v.replace(real, mask)
                # "컬럼비아 대학원(GSAPP)" 을 넘겨도 모델은 "컬럼비아 대학교" 로 풀어 쓴다.
                # 괄호·수식어를 뗀 알맹이도 같이 가린다.
                # "Jasmin (Jia-Chen) Lin" 처럼 여러 토막인 이름은 성만 따로 쓰이기도 한다.
                # 학교도 "컬럼비아 대학원(GSAPP)" 을 넘기면 "컬럼비아 대학교" 로 풀어 쓴다.
                for tok in re.split(r"[()（）,·\s]+", real.strip()):
                    if len(tok) >= 2:
                        v = v.replace(tok, mask)
                v = re.sub(rf"(?:{re.escape(mask)}[\s·]*)+", mask, v)
        return v
    if isinstance(v, list):
        return [_redact(x) for x in v]
    if isinstance(v, dict):
        return {k: _redact(x) for k, x in v.items()}
    return v


@dataclass
class Row:
    """사이트에 실리는 공고 한 건 — 원본 payload 와 우리가 매긴 판정을 함께 들고 있다."""
    payload: dict
    posting: Posting
    office: object
    country: str
    assess: object
    elig: object
    fit: tuple
    pay: dict
    grade: str
    grade_why: str
    sent_at: str = ""


def _load_rows():
    offs = load_offices()
    by = {o.id: o for o in offs}
    db = ROOT / "store" / "radar.sqlite"
    sent, hashes, conn = [], {}, None
    if db.exists():
        conn = sqlite3.connect(db)
        sent = [(json.loads(p), t) for p, t in
                conn.execute("SELECT payload, sent_at FROM sent_posting")]
        hashes = {r[0]: r for r in conn.execute("SELECT office_id,hash,checked_at FROM page_hash")}
    return offs, by, sent, hashes, conn


def selected() -> list[Row]:
    """**사이트에 실리는 공고 한 벌.** 텔레그램 재발송도 이 목록을 그대로 쓴다.

    거르는 기준을 두 군데에 두면 웹과 봇이 어긋난다 — 실제로 어긋나 있었다."""
    _offs, by, sent, _h, conn = _load_rows()
    if conn:
        conn.close()
    rows: list[Row] = []
    for d, sent_at in sent:
        p = Posting(**d)
        verified.apply(p)          # 확인된 사실이 있으면 저장분보다 우선한다
        d = {**d, **p.model_dump()}
        off = by.get(p.office_id)
        if off is None:
            continue
        pc = country_of(p, off.country)
        a = assess(p, pc, off)
        if not is_new_grad_ok(a, p.track):
            continue   # 경력직은 사이트에도 싣지 않는다
        if relevance.career_only(p) or relevance.special_track(p):
            continue
        if relevance.is_low_fit(relevance.label(p, off)):
            continue   # 설계직 아님·시공사
        if not relevance.worth_applying(p, off)[0]:
            continue   # 이름 모를 사무소는 사이트에도 싣지 않는다 (발송 기준과 동일)
        if relevance.drop_for_no_degree(p, off):
            continue   # 학력무관 공고는 사이트에도 싣지 않는다 (발송 단계와 같은 기준)
        grade, grade_why = relevance.firm_grade(p, off)
        if grade == "weak":
            continue
        rows.append(Row(
            payload=d, posting=p, office=off, country=pc, assess=a,
            elig=eligibility.judge(p, pc), fit=relevance.fit_grade(p, off, a),
            pay=salary.describe(p, pc, off.tier, off.id),
            grade=grade, grade_why=grade_why, sent_at=sent_at,
        ))
    return dedup(rows)


def _richness(x: dict) -> tuple:
    """내용이 더 채워진 판독을 남긴다 — 빈 판독이 채워진 판독을 덮으면 안 된다."""
    return (
        sum(1 for k in ("qualifications", "responsibilities", "preferred",
                        "software", "firm_projects") if x.get(k)),
        0 if x.get("gate") == "ask" else 1,     # 판정이 선 쪽을 우선한다
        len(json.dumps(x, ensure_ascii=False)),
    )


def dedup(rows: list[Row]) -> list[Row]:
    """같은 공고가 두 번 실리는 일이 있다. 잡보드에서 목록 URL 로 한 번, 상세 URL 로
    또 한 번 들어오면 키가 갈린다. 회사+제목이 같으면 한 건으로 합친다."""
    out: dict[tuple, Row] = {}
    for r in rows:
        k = ("".join((r.payload.get("company") or r.office.display_name or "").split()).lower(),
             "".join((r.payload.get("title") or "").split()).lower())
        cur = out.get(k)
        if cur is None or _richness({**r.payload, "gate": r.elig.gate}) > \
                _richness({**cur.payload, "gate": cur.elig.gate}):
            out[k] = r
    return list(out.values())


def build() -> dict:
    offs, by, sent, hashes, c = _load_rows()

    offices = []
    for o in offs:
        h = hashes.get(o.id)
        offices.append({
            "id": o.id, "country": o.country, "name": o.display_name,
            "name_local": (o.name.get("ko") or o.name.get("ja") or o.name.get("zh")
                           or o.display_name),
            "city": o.city, "tier": o.tier, "url": o.careers_url,
            "checked_at": h[2] if h else None,
            "status": "ok" if (h and h[1]) else ("fail" if h else "untracked"),
        })

    posts = []
    for r in selected():
        d, p, off, a, e = r.payload, r.posting, r.office, r.assess, r.elig
        fit_grade, fit_why = r.fit
        posts.append({
            # _outreach 원본(실명이 들어 있다)이 그대로 실리지 않게 밑줄 키는 빼고 펼친다.
            # 아래에서 가린 사본만 "outreach" 로 싣는다.
            **{k: v for k, v in d.items() if not k.startswith("_")},
            "country": r.country, "office_name": off.display_name,
            "office_tier": off.tier, "sent_at": r.sent_at,
            "verdict": a.verdict, "expired": a.expired,
            "blockers_desc": a.blockers_desc, "soft_desc": a.soft_desc,
            "met": a.met, "unknowns": a.unknowns,
            "gate": e.gate, "gate_icon": e.icon, "gate_label": e.label("ko"),
            # 이름을 모르는 채로 공개 사이트에 메일 초안을 싣지 않는다.
            # (워크플로에서 시크릿을 안 넘기면 여기서 통째로 빠진다)
            "outreach": _redact(d.get("_outreach")) if _identity_known() else None,
            # 세 언어 번역 (tools/translate_postings.py 가 넣는다). 해시는 내부용이라 뺀다.
            # **번역본에도 이름·학교를 가린다.** 메일 초안이 통째로 옮겨져 있어서,
            # 여기를 빼먹으면 원문만 가리고 번역본으로 실명이 새어 나간다 (실제로 그랬다).
            "i18n": (_redact({k: v for k, v in (d.get("_i18n") or {}).items() if k != "hash"})
                     if _identity_known() else None) or None,
            "grade": r.grade, "grade_why": r.grade_why, "pay": r.pay,
            "fit": fit_grade, "fit_why": fit_why,
            "gate_reason": e.reason, "gate_evidence": e.evidence, "gate_action": e.action,
        })

    # 아카이브(과거 공고) — LLM 을 거치지 않고 목록에서 직접 긁은 가벼운 기록이다.
    # JD 는 없지만 '누가 언제 뽑았나' 는 알 수 있어서 내년 시점을 잡는 데 쓰인다.
    archive = []
    if c is not None:
        try:
            for url, country, company, title, posted, deadline, src in c.execute(
                "SELECT url,country,company,title,posted_at,deadline,source FROM archive"
                " ORDER BY COALESCE(posted_at,'') DESC"
            ):
                archive.append({"url": url, "country": country or "KR", "company": company,
                                "title": title, "posted_at": posted, "deadline": deadline,
                                "source": src})
        except sqlite3.OperationalError:
            pass   # 아직 아카이브를 한 번도 안 돌렸다
        c.close()

    # ── 공고가 없는 사무소 ──────────────────────────────
    # 한국 아틀리에는 공고를 거의 내지 않는다. 상시로 포트폴리오를 받아 뽑는다.
    # 유현준건축사사무소는 자사 사이트가 아예 월간 SPACE 공고로 링크되어 있었다.
    # 공고를 기다리기만 하면 한국은 계속 비어 있다 — 그래서 따로 세운다.
    def _n(x: str) -> str:
        return "".join((x or "").split()).lower()

    posted_ids = {p.get("office_id") for p in posts}
    posted_names = {_n(p.get("company")) for p in posts if p.get("company")}

    open_apply = []
    for o in offs:
        if o.tier == "job_board" or o.id in posted_ids:
            continue
        names = [v for v in (o.name or {}).values()]
        if any(_n(v) and any(_n(v) in pn or pn in _n(v) for pn in posted_names) for v in names):
            continue
        h = hashes.get(o.id)
        if not o.careers_url:
            why = "채용 페이지 주소를 아직 못 찾았다"
        elif h and h[1]:
            why = "채용 페이지는 보고 있는데 지금 올라온 공고가 없다"
        else:
            why = "채용 페이지를 읽지 못했다 (자바스크립트 등)"
        open_apply.append({
            "id": o.id, "country": o.country, "tier": o.tier,
            "name": o.display_name,
            "name_local": (o.name.get("ko") or o.name.get("ja") or o.name.get("zh")
                           or o.display_name),
            "city": o.city, "note": o.note,
            "site": o.raw.get("site"), "email": o.raw.get("apply_email"),
            "open_application": bool(o.raw.get("open_application")),
            "careers_url": o.careers_url, "why": why,
        })
    order = {"atelier": 0, "large": 1, "mid": 2, "global": 3}
    open_apply.sort(key=lambda x: (x["country"], order.get(x["tier"], 9), x["name"]))

    return {
        "open_apply": open_apply,
        "archive": archive,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offices": offices,
        "postings": posts,
    }


if __name__ == "__main__":
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    d = build()
    (docs / "data.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    g = {}
    for p in d["postings"]:
        g[p["gate"]] = g.get(p["gate"], 0) + 1
    print(f"data.json  공고 {len(d['postings'])}건  상시지원 {len(d['open_apply'])}곳  사무소 {len(d['offices'])}곳  게이트 {g}")
