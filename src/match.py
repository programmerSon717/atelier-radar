"""공고에 라벨을 붙인다. 거르지 않는다 (B안) — 판단은 사람이 한다.

언어 판정은 정규식으로 자연어를 파싱하지 않는다. 그건 "fluency in Korean,
business-level Japanese/English" 같은 문장에서 반드시 틀린다.
추출 단계의 모델이 requires_japanese / requires_korean 을 직접 채우게 하고,
그 값이 없을 때만 정규식으로 보조한다.

blocker 는 두 종류다:
  hard — 지금 지원해도 떨어지는 조건 (경력 미달, 졸업시기 불일치, 언어 필수 미보유)
  soft — 준비하면 넘을 수 있는 조건 (한국어, 비자 자력 해결)
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from . import clock, relevance
from .models import Posting

Verdict = Literal["fit", "conditional", "blocked", "unknown", "expired"]

JP_LANG = re.compile(r"日本語|japanese|JLPT|일본어", re.I)
KO_LANG = re.compile(r"한국어|korean|TOPIK|韓国語", re.I)
ZH_LANG = re.compile(r"中文|mandarin|chinese|중국어", re.I)
EN_ONLY = re.compile(r"english[ -]?only|영어만|英語のみ", re.I)

EXP_YEARS = re.compile(r"(\d+)\s*(?:\+|년|年|years?)", re.I)
VAGUE_EXP = re.compile(r"a few years|several years|수년|数年|數年", re.I)

# 중화권·일본 공고는 경력 연수를 한자로 쓴다. "三年以上之工作經驗" 을 못 읽으면
# 경력직 공고가 신입 공고인 채로 새어 나간다 (실제로 2건이 발송됐다).
HAN_DIGITS = {"一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
HAN_YEARS = re.compile(r"([一二三四五六七八九十兩两]{1,3})\s*(?:年|년)")

# "経験3年以下" 는 상한(第二新卒 자격)이지 요구 경력이 아니다.
# 이걸 하한으로 읽으면 자격 있는 신입 공고를 숨겨버린다.
EXP_CEILING = re.compile(r"以下|未満|以内|이하|미만|이내|or less|under|up to|less than|within", re.I)
EXP_FLOOR = re.compile(r"以上|이상|\+|or more|at least|minimum|이상의", re.I)
NEW_GRAD_OK = re.compile(r"신입|新卒|新鮮人|未経験|應屆|no experience|entry[ -]?level|new grad|fresh grad", re.I)


ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


@dataclass
class Assessment:
    verdict: Verdict
    labels: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)       # hard — 지금 지원해도 떨어진다
    soft_blockers: list[str] = field(default_factory=list)  # 준비하면 넘을 수 있는 것
    unknowns: list[str] = field(default_factory=list)       # 공고에 안 적혀 확인이 필요한 것
    met: list[str] = field(default_factory=list)            # 충족하는 조건
    blockers_desc: list[str] = field(default_factory=list)  # 막는 이유(사람이 읽는 문장)
    soft_desc: list[str] = field(default_factory=list)      # 준비하면 넘는 것(문장)
    expired: bool = False


def _deadline_check(p: Posting, a: Assessment, country: str) -> None:
    """이미 마감된 공고를 새 공고처럼 보내면 안 된다.
    다만 버리지도 않는다 — "이 회사 공채는 8월에 마감된다"는 것 자체가
    내년을 준비하는 데 필요한 정보다."""
    if not p.deadline:
        return
    left = clock.days_left(p.deadline, country)
    if left is None:
        return
    if left < 0:
        a.expired = True
        m = ISO_DATE.search(p.deadline)
        a.blockers_desc.append(
            f"이미 마감됨 ({m.group(0)} 현지시각) — 다음 사이클 참고용")


def _flag(explicit: Optional[bool], pattern: re.Pattern, text: str) -> Optional[bool]:
    """모델이 채운 값이 있으면 그걸 쓰고, 없을 때만 정규식으로 추정한다."""
    if explicit is not None:
        return explicit
    return True if pattern.search(text) else None


def _language_check(p: Posting, a: Assessment) -> None:
    req = p.language_required
    text = req or ""

    if p.english_only_ok is True or EN_ONLY.search(text):
        a.met.append("영어로 업무 가능")
        return

    needs_ja = _flag(p.requires_japanese, JP_LANG, text)
    needs_ko = _flag(p.requires_korean, KO_LANG, text)

    if needs_ja is None and needs_ko is None and not req:
        a.unknowns.append("언어 요건 미기재")
        return

    # 요건 원문은 항상 그대로 보여준다 — 라벨이 틀렸을 때 사람이 바로 잡을 수 있게
    if req:
        a.unknowns.append(f"언어 요건: {req}")
    if needs_ja:
        a.blockers_desc.append("일본어 필수 — 현재 미보유")
        a.blockers.append("일본어 없음")
    if needs_ko:
        a.soft_desc.append("한국어 필수 — 현재 초급")
        a.soft_blockers.append("한국어 초급")
    if not needs_ja and not needs_ko and ZH_LANG.search(text):
        a.labels.append("중국어 요건 — 네이티브 (충족)")


def _han_years(text: str) -> Optional[int]:
    """한자로 쓴 경력 연수를 읽는다. 三年 → 3, 十年 → 10, 二十年 → 20."""
    m = HAN_YEARS.search(text)
    if not m:
        return None
    s = m.group(1)
    if "十" in s:
        tens, _, ones = s.partition("十")
        return (HAN_DIGITS.get(tens, 1) if tens else 1) * 10 + (HAN_DIGITS.get(ones, 0) if ones else 0)
    return HAN_DIGITS.get(s)


def _experience_check(p: Posting, a: Assessment) -> None:
    req = p.experience_required
    if not req:
        # 요건란이 비어도 제목에 "3年以上" 처럼 박힌 공고가 있다. 추출이 놓치면 여기서 잡는다.
        title = p.title or ""
        if (EXP_YEARS.search(title) or HAN_YEARS.search(title)) and EXP_FLOOR.search(title):
            req = title
        else:
            return
    if NEW_GRAD_OK.search(req):
        a.met.append(f"신입 가능 — {req}")
        return
    m = EXP_YEARS.search(req)
    years = int(m.group(1)) if m else _han_years(req)
    if years is not None and EXP_CEILING.search(req):
        # 상한 조건 — 경력 0년은 당연히 충족한다
        a.met.append(f"경력 {years}년 이하 대상 — {req}")
        return
    # "2027년 졸업예정자" 의 2027 을 요구 경력으로 읽으면 안 된다.
    # 경력 연수는 현실적으로 두 자리를 넘지 않고, 연도는 네 자리다. 크기로 가른다.
    # ("경력 5년" 처럼 '이상' 을 생략하는 표기가 한국어에 흔해서 하한 표시를 요구할 수 없다)
    if years is not None and 1 <= years <= 40:
        a.blockers_desc.append(f"경력 {years}년 요구 — {req}")
        a.blockers.append("정규직 경력 0년")
    elif VAGUE_EXP.search(req):
        a.blockers_desc.append(f"경력직 요건 — {req}")
        a.blockers.append("정규직 경력 0년")
    else:
        a.unknowns.append(f"경력 요건 불명확: {req}")


def _timing_check(p: Posting, a: Assessment, country: str) -> None:
    """2027년 5월 졸업. 일본 4월 일괄 입사와 어긋나는 건이 핵심."""
    gy = p.grad_year_required or ""
    if country == "JP" and re.search(r"2027年4月|2027年卒", gy):
        a.blockers_desc.append(f"{gy} — 2027년 5월 졸업이라 4월 입사 불가")
        a.blockers.append("졸업 시기 불일치")
    elif gy:
        a.unknowns.append(f"졸업연도 조건: {gy}")


def _visa_check(p: Posting, a: Assessment, country: str) -> None:
    if country == "TW":
        return  # 대만 국적 — 비자 무관
    if p.visa_sponsorship is False:
        # 스폰서가 없다고 지원이 막히는 건 아니다. 본인이 비자를 구해야 할 뿐.
        a.soft_desc.append("비자 스폰서 없음 — 본인이 해결해야 함")
        a.soft_blockers.append("비자 자력 해결 필요")
    elif p.visa_sponsorship is True:
        a.met.append("비자 스폰서 있음")


# 인턴은 정의상 경력직이 아니다. 공고 문구에 "professional experience" 같은 말이
# 섞여 있어도(주로 우대사항이다) 경력직으로 걸러버리면 안 된다.
INTERN_TRACKS = {"intern", "intern_to_fulltime"}


def is_new_grad_ok(a: "Assessment", track: str | None = None) -> bool:
    """신입(0년차)이 지원할 수 있는 공고인가.

    후보자는 경력이 0년이다. 경력을 요구하는 공고는 지원 자체가 안 되므로
    라벨만 붙여 보내지 않고 아예 내보내지 않는다. 단 인턴은 예외다."""
    if track in INTERN_TRACKS:
        return True
    return "정규직 경력 0년" not in a.blockers


def assess(p: Posting, country: str, office=None) -> Assessment:
    a = Assessment(verdict="unknown")
    if office is None:  # 국가만 아는 경우를 위한 최소 대역
        office = type("O", (), {"country": country})()
    _language_check(p, a)
    _experience_check(p, a)
    _timing_check(p, a, country)
    _visa_check(p, a, country)

    _deadline_check(p, a, country)
    a.labels.extend(relevance.label(p, office))
    if relevance.is_low_fit(a.labels):
        a.soft_blockers.append("직무 적합성 낮음")

    if p.confidence == "unverified":
        a.unknowns.append("미검증 — 출처를 직접 확인할 것")

    a.labels = a.blockers_desc + a.soft_desc + a.met + a.unknowns

    if a.expired:
        a.verdict = "expired"
    elif a.blockers:
        a.verdict = "blocked"
    elif a.soft_blockers or a.unknowns:
        a.verdict = "conditional"
    else:
        a.verdict = "fit"
    return a
