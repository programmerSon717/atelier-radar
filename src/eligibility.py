"""외국인이 지원할 수 있는가 — 이 봇에서 가장 중요한 판정.

후보자는 대만 국적이고 한국어는 초급, 일본어는 못 한다.
그래서 "공고가 좋은가" 보다 "애초에 지원이 되는가" 가 먼저다.

원칙: 공고에 안 적힌 것을 추측하지 않는다.
한국·일본 공고 대부분은 외국인 채용을 언급하지 않는다. 그건 '불가'가 아니라
'모른다'이고, 모르는 건 모른다고 표시해서 사람이 직접 문의하게 한다.
"""
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
    "domestic": "국내 대학 유학생 전형 — 해당 없음",
    "closed": "외국인 지원 불가",
}
LABEL_ZH = {
    "open": "開放外籍應徵",
    "ask": "未提及外籍 — 需詢問",
    "native": "需語言檢定·當地語言 — 實質門檻",
    "domestic": "限當地大學留學生 — 不符",
    "closed": "不開放外籍",
}


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
        return Eligibility("open", "대만 국적 — 비자·언어 장벽 없음")

    # 공고가 명시적으로 배제한 경우
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

    # 어학시험 급수를 요구하면 그것부터 넘어야 한다
    if posting.language_test and country in ("KR", "JP"):
        return Eligibility(
            "native",
            f"어학시험 요구 — {posting.language_test}",
            posting.foreigner_evidence or posting.language_test,
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

    # 영어만으로 가능하다고 적혀 있으면 사실상 열려 있다
    if posting.english_only_ok:
        return Eligibility("open", "영어로 업무 가능 명시",
                           posting.language_required, "바로 지원 가능")

    # 여기까지 오면 공고에 아무 말이 없는 것 — 대다수가 여기 해당한다
    return Eligibility(
        "ask",
        "공고에 외국인 채용·비자·언어 언급이 전혀 없음",
        None,
        "채용 담당자에게 외국인 지원 가능 여부와 비자 스폰서 여부를 먼저 문의할 것",
    )
