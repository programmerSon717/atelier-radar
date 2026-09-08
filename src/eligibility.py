"""외국인이 지원할 수 있는가 — 이 봇에서 가장 중요한 판정.

후보자는 대만 국적이고 한국어는 초급, 일본어는 못 한다.
그래서 "공고가 좋은가" 보다 "애초에 지원이 되는가" 가 먼저다.

원칙: 공고에 안 적힌 것을 추측하지 않는다.
한국·일본 공고 대부분은 외국인 채용을 언급하지 않는다. 그건 '불가'가 아니라
'모른다'이고, 모르는 건 모른다고 표시해서 사람이 직접 문의하게 한다.
"""
import re
from dataclasses import dataclass
from typing import Literal, Optional

# open     = 지원 가능 (근거 있음)
# ask      = 공고에 언급 없음 — 직접 문의해야 함
# native   = 어학시험·현지어가 벽
# domestic = 외국인은 뽑지만 '국내 대학 유학생' 대상이라 해당 없음
# closed   = 지원 불가 (근거 있음)
Gate = Literal["open", "ask", "native", "domestic", "closed"]

# 색깔 공은 정보를 담지 않으면서 자리만 차지한다. 상태를 그대로 말하는 기호를 쓴다.
ICON = {"open": "✅", "ask": "❔", "native": "🈲", "domestic": "🎓", "closed": "⛔"}
LABEL_KO = {
    "open": "외국인 지원 가능",
    "ask": "외국인 채용 언급 없음 — 문의 필요",
    "native": "어학시험·현지어 요구 — 사실상 장벽",
    "domestic": "국내 대학 졸업·유학생 전형 — 해당 없음",
    "closed": "외국인 지원 불가",
}
LABEL_ZH = {
    "open": "開放外籍應徵",
    "ask": "未提及外籍 — 需詢問",
    "native": "需語言檢定·當地語言 — 實質門檻",
    "domestic": "限當地大學畢業·留學生 — 不符",
    "closed": "不開放外籍",
}


# ── 모델 판단을 믿지 않고 원문에서 직접 잡는 것들 ──────────────
# 추출 모델은 같은 페이지를 두 번 읽어도 다르게 답한다. 실제로 현대건설 유학생 공고가
# 한 번은 target 을 채웠고 한 번은 비웠다. 비면 "✅ 지원 가능" 으로 나간다.
# 사람이 지원했다가 서류에서 잘리는 종류의 실수라 정규식으로 못을 박는다.

# 한국·일본의 "외국인 유학생 채용" 은 자국 대학에 다닌 유학생 전형이다.
# 미국 대학 졸업자를 부르는 말이 아니다.
# 어학시험이라고 다 벽이 아니다. 후보자는 영어가 능통하다 — TOEIC 700 은 넘는 조건이지
# 막는 조건이 아니다. 막는 건 한국어·일본어 시험이다. 갈라서 보지 않으면
# 현대건설 일반 공채처럼 지원 가능한 자리를 "사실상 장벽" 으로 잘라낸다.
LOCAL_TEST = re.compile(r"TOPIK|한국어\s*능력|한국어능력시험|JLPT|日本語能力|"
                        r"일본어\s*능력|한자능력", re.I)
# "영어 능통자 우대/필수" 는 외국인을 받는다는 뜻이 아니다. 그냥 영어를 요구하는 것이다.
# 실제로 반 시게루 인턴십을 "영어로 업무 가능 명시 → 지원 가능" 으로 내보냈는데,
# 근거로 든 문장은 "Fluent in English (written and spoken)" — 지원 자격 요구였다.
# 현지어가 필요 없다고 말한 경우에만 장벽이 없다고 본다.
ENGLISH_ENOUGH = re.compile(
    r"英語のみ|英語だけ|語学力は問いません|日本語(?:能力)?は?\s*(?:不問|問いません|不要)|"
    r"한국어\s*(?:불문|무관|불필요)|국적\s*무관|"
    r"不限語言|不限國籍|中文\s*不拘|"
    r"english[- ]?only|no\s+japanese\s+(?:required|necessary)|"
    r"japanese\s+(?:is\s+)?not\s+required|without\s+japanese|"
    r"regardless\s+of\s+nationality|any\s+nationality", re.I)

ENGLISH_TEST = re.compile(r"TOEIC|TOEFL|OPI[Cc]?|IELTS|TEPS|텝스|토익|토플|오픽", re.I)

INTL_STUDENT = re.compile(r"유학생|留学生|외국인\s*유학|外国人留学", re.I)

# 출신 대학 소재지 요건. 이 문구 하나가 후보자를 통째로 배제한다.
DOMESTIC_DEGREE = re.compile(
    r"국내\s*(?:정규\s*)?[24]년제|국내\s*정규\s*대학|국내\s*소재\s*대학|"
    r"국내\s*대학\s*(?:졸업|재학|학위)|국내\s*대학교\s*졸업|"
    r"日本国内の大学|国内の大学を(?:卒業|修了)", re.I)


def _blob(posting) -> str:
    """모델이 지어낸 산문(summary·notes)은 빼고 공고 원문에서 온 것만 모은다."""
    return " ".join(filter(None, [
        posting.title, posting.education_required, posting.foreigner_evidence,
        posting.domestic_degree_evidence, posting.language_required,
        *(posting.qualifications or []), *(posting.preferred or []),
    ]))


@dataclass
class Eligibility:
    gate: Gate
    reason: str            # 왜 이렇게 판정했는지 (사람이 읽는 한 줄)
    evidence: Optional[str] = None   # 공고 원문 근거
    action: Optional[str] = None     # 지원자가 다음에 할 일

    @property
    def icon(self) -> str:
        return ICON[self.gate]

    def label(self, locale: str = "ko") -> str:
        return (LABEL_ZH if locale == "zh_TW" else LABEL_KO)[self.gate]


def judge(posting, country: str) -> Eligibility:
    """공고 + 국가 → 지원 가능 여부."""
    # 대만은 후보자 국적이라 애초에 외국인 문제가 없다
    if country == "TW":
        return Eligibility(
            "open",
            "대만 국적이라 국적·비자 요건 자체가 없다 (공고가 외국인 채용을 말한 것은 아님)",
            None,
            "국적 문제는 없다. 남은 건 자격 요건뿐이다",
        )

    blob = _blob(posting)

    # 모델이 domestic_degree_required 를 안 채워도 원문에 문구가 있으면 그걸 믿는다
    m = DOMESTIC_DEGREE.search(blob)
    if m and posting.domestic_degree_required is not False:
        return Eligibility(
            "domestic",
            "국내(한국/일본) 대학 졸업 요건 — 미국 대학 졸업자는 지원 자격 자체가 없음",
            posting.domestic_degree_evidence or f"공고 원문: …{m.group(0)}…",
            "이 공고는 건너뛰어라. 해외대 졸업자를 받는 글로벌·해외인재 전형을 따로 찾아야 한다",
        )

    # ★★ 출신 대학 소재지 요건이 가장 먼저다. 이게 걸리면 다른 조건은 볼 필요도 없다.
    # "국내 정규 4년제 대학 졸업자" 는 미국 대학 졸업자를 통째로 배제한다.
    if posting.domestic_degree_required is True:
        return Eligibility(
            "domestic",
            "국내(한국/일본) 대학 졸업 요건 — 미국 대학 졸업자는 지원 자격 자체가 없음",
            posting.domestic_degree_evidence,
            "이 공고는 건너뛰어라. 해외대 졸업자를 받는 글로벌·해외인재 전형을 따로 찾아야 한다",
        )

    # 공고가 명시적으로 배제한 경우 (출신 대학 요건보다 뒤에 본다 —
    # '국내 대학 졸업' 이 걸려 있으면 비자를 따지기 전에 이미 자격이 없다)
    if posting.foreigner_eligible is False:
        return Eligibility("closed", "공고에 외국인 지원 불가 명시",
                           posting.foreigner_evidence,
                           "다른 공고를 보는 편이 낫다")
    if posting.visa_sponsorship is False and country in ("KR", "JP"):
        return Eligibility("closed", "취업비자 스폰서 불가 명시",
                           posting.foreigner_evidence,
                           "이미 취업 가능한 비자가 있어야 지원 가능")

    # ★ 외국인을 뽑더라도 "어떤 외국인" 인지가 갈린다.
    # 한국·일본의 외국인 채용은 대부분 자국 대학에 다닌 유학생 대상이다.
    # 후보자는 미국 대학 졸업이라 그 전형에는 해당하지 않는다.
    if posting.foreigner_target == "domestic_intl_student":
        return Eligibility(
            "domestic",
            "국내(한국/일본) 대학 유학생 대상 전형 — 미국 대학 졸업자는 해당 없음",
            posting.foreigner_evidence or posting.language_test,
            "해외대 졸업자도 되는지 문의하거나, 글로벌·해외인재 전형을 따로 찾을 것",
        )

    # "외국인 유학생 채용" 이라고 적힌 공고를 모델이 target 없이 넘겨도 open 으로 보내지 않는다.
    # 해외대 졸업자 대상이라고 공고가 스스로 밝힌 경우에만 예외다.
    if country in ("KR", "JP") and INTL_STUDENT.search(blob) \
            and posting.foreigner_target != "overseas_grad":
        return Eligibility(
            "domestic",
            "외국인 '유학생' 전형 — 한국·일본에서는 자국 대학 재학·졸업 외국인 대상이다",
            posting.foreigner_evidence or posting.title,
            "해외대 졸업자도 지원되는지 반드시 먼저 확인할 것. 대개는 해당되지 않는다",
        )

    # 현지어 시험을 요구하면 그것부터 넘어야 한다.
    # 영어 시험(TOEIC·OPIc 등)은 넘는 조건이라 여기서 막지 않는다.
    lt = posting.language_test or ""
    if lt and country in ("KR", "JP") and LOCAL_TEST.search(lt):
        return Eligibility(
            "native",
            f"현지어 시험 요구 — {lt}",
            posting.foreigner_evidence or lt,
            "해당 급수를 먼저 확보해야 지원 가능",
        )

    # 공고가 명시적으로 허용한 경우
    if posting.foreigner_eligible is True or posting.visa_sponsorship is True:
        why = "공고에 외국인 지원 가능 명시"
        if posting.foreigner_target == "overseas_grad":
            why = "해외 대학 졸업자 대상 전형 — 조건 부합"
        return Eligibility("open", why, posting.foreigner_evidence, "바로 지원 가능")

    # 언어가 벽인 경우 — 지원은 되지만 현실적으로 막힌다
    if posting.requires_japanese:
        return Eligibility("native", "일본어 필수 — 현재 미보유",
                           posting.language_required,
                           "영어 가능 아틀리에·외국계를 먼저 볼 것")
    if posting.requires_korean:
        return Eligibility("native", "한국어 필수 — 현재 초급",
                           posting.language_required,
                           "2027년까지 TOPIK 확보하면 열림")

    # 영어만으로 가능하다고 **공고가 말한 경우에만** 열려 있다고 본다.
    # 모델이 english_only_ok 를 켜도 근거 문장이 "영어 능통 필수" 면 그건 요구 조건이다.
    if posting.english_only_ok:
        ev = " ".join(filter(None, [posting.language_required, posting.foreigner_evidence, blob]))
        m2 = ENGLISH_ENOUGH.search(ev)
        if m2:
            return Eligibility("open", "현지어 없이도 된다고 공고에 적혀 있음",
                               posting.language_required or m2.group(0), "바로 지원 가능")
        return Eligibility(
            "ask",
            "영어 관련 언급은 있으나 외국인 지원 가능 여부는 적혀 있지 않음",
            posting.language_required,
            "영어만으로 지원·근무가 되는지 담당자에게 확인할 것",
        )

    # 여기까지 오면 공고에 아무 말이 없는 것 — 대다수가 여기 해당한다
    return Eligibility(
        "ask",
        "공고에 외국인 채용·비자·언어 언급이 전혀 없음",
        None,
        "채용 담당자에게 외국인 지원 가능 여부와 비자 스폰서 여부를 먼저 문의할 것",
    )
