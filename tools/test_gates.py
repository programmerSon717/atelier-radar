"""게이트 회귀 검사 — 손대고 나서 반드시 돌린다.

  ./.venv/bin/python tools/test_gates.py

여기 있는 건 전부 실제로 한 번 틀렸던 것들이다.
경력직 2건이 신입 공고로 발송됐고(한자 숫자), 営業職 이 설계직으로 통과했다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Posting
from src.match import assess, is_new_grad_ok
from src.relevance import no_degree_required, fit_grade
from src.outreach import natural_name
from src.targets import load_offices

fails: list[str] = []


def P(**kw) -> Posting:
    kw.setdefault("office_id", "x"); kw.setdefault("title", "직원 모집")
    kw.setdefault("track", "entry_level"); kw.setdefault("source_url", "http://x")
    kw.setdefault("summary", "학력·경력 조건은 언급되지 않음")   # 부정문 오탐 방지용
    kw.setdefault("confidence", "confirmed")
    return Posting(**kw)


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: {got!r} ≠ {want!r}")


# ── 경력 요건 (한자 숫자 포함) ─────────────────────────────────
for req, want in [
    ("三年以上之工作經驗", False), ("兩年以上之工作經驗", False), ("十年以上の実務経験", False),
    ("二十年以上", False), ("5년 이상 경력", False), ("數年의 실무 경험", False),
    ("경력 3년 이하", True), ("신입 가능", True), ("2027년 졸업예정자", True),
    ("未経験可", True), ("経験3年以下（第二新卒）", True),
]:
    p = P(experience_required=req)
    check(f"경력[{req}]", is_new_grad_ok(assess(p, "TW"), p.track), want)

# 요건란이 비어도 제목에 박힌 경력은 잡는다
for title, want in [("建築設計師3年以上(台南)", False), ("建築設計師", True),
                    ("2027년 신입 공채", True), ("2027年卒 新卒採用", True)]:
    p = P(title=title)
    check(f"제목경력[{title}]", is_new_grad_ok(assess(p, "TW"), p.track), want)

# 인턴은 경력 문구가 있어도 통과한다
p = P(track="intern", experience_required="三年以上")
check("인턴 예외", is_new_grad_ok(assess(p, "TW"), p.track), True)

# ── 학력무관 ────────────────────────────────────────────────
for kw, want in [
    (dict(education_required="학력무관"), True), (dict(education_required="學歷不拘"), True),
    (dict(education_required="学歴不問"), True), (dict(qualifications=["학력 무관"]), True),
    (dict(education_required="대졸 이상"), False),
    (dict(qualifications=["국내 대학 졸업 여부 무관"]), False),   # 이건 학력무관이 아니다
    (dict(), False),
]:
    check(f"학력[{kw}]", bool(no_degree_required(P(**kw))), want)

# ── 회사명 다듬기 ───────────────────────────────────────────
for raw, want in [("(주)플랜엠", "플랜엠"), ("㈜건축사사무소리옹", "건축사사무소리옹"),
                  ("주식회사에프에이건축사사무소", "에프에이건축사사무소"),
                  ("NOMURA Co., Ltd.", "NOMURA"),
                  ("株式会社大林組", "株式会社大林組"),        # 일본어는 그대로가 정상
                  ("宗邁建築師事務所股份有限公司", "宗邁建築師事務所")]:
    check(f"회사명[{raw}]", natural_name(raw), want)

# ── 추천도 ─────────────────────────────────────────────────
offs = {o.id: o for o in load_offices()}
atelier = next(o for o in offs.values() if o.tier == "atelier")
p = P(title="建築設計 新卒", responsibilities=["美術館の設計"], office_id=atelier.id)
check("추천(아틀리에+포트폴리오 접점)", fit_grade(p, atelier, assess(p, atelier.country))[0], "recommend")

p = P(title="営業職", office_id=atelier.id)
check("비추천(설계직 아님)", fit_grade(p, atelier, assess(p, atelier.country))[0], "avoid")

p = P(title="건축설계", company="○○종합건설(주)", office_id=atelier.id)
check("비추천(시공사)", fit_grade(p, atelier, assess(p, atelier.country))[0], "avoid")

# 우리가 직접 고른 아틀리에는 근거가 부족해도 추천으로 둔다 (이미 검증된 곳이다)
p = P(title="설계 담당", office_id=atelier.id)
check("추천(우선 추적 사무소)", fit_grade(p, atelier, assess(p, atelier.country))[0], "recommend")

# 잡보드에서 주워 온 이름 모를 사무소는 근거가 없으면 중립이다
board = next(o for o in offs.values() if o.tier == "job_board")
p = P(title="설계 담당", company="○○건축사사무소", office_id=board.id)
check("중립(근거 부족)", fit_grade(p, board, assess(p, board.country))[0], "neutral")

# ── 사람이 확인한 사실 · 졸업 시기 · 어학 구분 ────────────────
from src import verified, eligibility                                    # noqa: E402

hd = P(title="2026년 하반기 현대건설 외국인 유학생 채용", track="entry_level",
       source_url="https://www.jobkorea.co.kr/Recruit/GI_Read/49896644?listno=4")
verified.apply(hd)
check("현대건설 유학생 — 국내대 요건", eligibility.judge(hd, "KR").gate, "domestic")
check("현대건설 유학생 — 졸업시기", "졸업 시기 불일치" in assess(hd, "KR").blockers, True)

hg = P(title="2026년 하반기 현대건설 신입사원 채용", track="entry_level",
       source_url="https://www.jobkorea.co.kr/Recruit/GI_Read/49895957")
verified.apply(hg)
# 영어 시험(TOEIC)은 막는 조건이 아니다 — 후보자는 영어 능통이다
check("영어 시험은 장벽이 아니다", eligibility.judge(hg, "KR").gate, "ask")
check("영어 시험은 충족 조건", any("영어 시험" in m for m in assess(hg, "KR").met), True)

# 한국어 시험은 벽이다
ko = P(title="신입 채용", language_test="TOPIK 4급 이상")
check("TOPIK 은 장벽", eligibility.judge(ko, "KR").gate, "native")

# ── 번역 뒤처리 ────────────────────────────────────────────
# 모델이 옮긴 값 뒤에 원문을 괄호로 붙여 놓는 일이 있다. gate_evidence 에서만 맞다.
# 주소·날짜처럼 진짜 정보가 든 괄호까지 떼면 안 된다.
from src import i18n as _i18n                                       # noqa: E402
_t = {"zh_TW": {
    "gate_reason": "公告中完全未提及外籍應徵 (원문: 공고에 외국인 채용 언급이 없음)",
    "unknowns": ["公告未載明語言要求 (언어 요건 미기재)"],
    "pay_stated": "詳細資訊請查看 My Page (詳細はマイページをご確認ください)",
    "location": "首爾 西大門區 城山路 559 (代新洞, 珍솔大樓) 4樓",
    "employment_type": "正職 (2026年4月入社)",
    "gate_evidence": "海外大學畢業 (原文: 海外の大学を卒業)",
}}
_i18n._strip_paren_original(_t)
_z = _t["zh_TW"]
check("옮긴 뒤 붙은 원문을 뗀다", _z["gate_reason"], "公告中完全未提及外籍應徵")
check("목록도 뗀다", _z["unknowns"], ["公告未載明語言要求"])
check("급여 문구도 뗀다", _z["pay_stated"], "詳細資訊請查看 My Page")
check("주소 괄호는 그대로 둔다", "代新洞" in _z["location"], True)
check("날짜 괄호는 그대로 둔다", _z["employment_type"], "正職 (2026年4月入社)")
check("판정 근거는 원문을 남긴다", "原文" in _z["gate_evidence"], True)

# ── 문구가 한곳에서 오는가 ──────────────────────────────────
# site/ui.js 는 config/locales/*.yaml 에서 생성된다. 손으로 고치면 웹과 봇이 갈린다.
from tools.build_ui import OUT as UI_JS, build as build_ui          # noqa: E402
check("site/ui.js 가 config/locales 와 같다",
      UI_JS.read_text(encoding="utf-8") == build_ui(), True)

# 봇이 쓰는 문구가 실제로 있는지 — 없으면 메시지에 키 이름이 그대로 찍힌다
from src.render import load_locale                                  # noqa: E402
_L = load_locale("zh_TW")
_need = ["g_open", "fit_recommend", "resp", "qual", "pref", "soft", "cond",
         "cond_employ", "cond_process", "cond_lang", "unknown_h", "contact_h",
         "projects", "pay", "pay_stated", "pay_ref", "pay_avg", "pay_src", "pay_none",
         "pay_noamt", "blockers", "softb", "met", "unknowns", "mail_h", "mail_subject",
         "mail_send_note", "hooks", "asks", "source", "thin", "deadline", "expired",
         "today_due", "due_in", "track_new_grad", "track_intern", "track_intern_ft",
         "track_year_round", "tier_other"]
check("봇이 쓰는 zh_TW 문구가 모두 있다",
      [k for k in _need if k not in (_L.get("web") or {})], [])
check("봇 전용 문구(해시태그·오류)가 있다",
      all(k in (_L.get("bot") or {}) for k in ("tag_country", "tag_track", "tag_gate", "errors")),
      True)

# ── 결과 ───────────────────────────────────────────────────
if fails:
    print(f"실패 {len(fails)}건")
    for f in fails:
        print("  ✗", f)
    raise SystemExit(1)
print("게이트 회귀 검사 통과")
