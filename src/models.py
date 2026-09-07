"""공고 스키마. 워커가 반드시 이 형태로만 답한다."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

Confidence = Literal["confirmed", "likely", "unverified"]


class Posting(BaseModel):
    """채용 공고 하나. 모든 사실 주장에는 source_url 이 붙어야 한다."""

    office_id: str = Field(description="data/targets/*.yaml 의 id")
    company: Optional[str] = Field(
        default=None,
        description="공고를 낸 회사 이름. 잡보드처럼 여러 회사가 섞인 페이지에서는 반드시 채운다. "
                    "특정 사무소 채용페이지면 비워도 된다",
    )
    title: str = Field(description="공고 제목 (원문 언어 그대로)")
    track: Literal[
        "new_grad", "intern", "intern_to_fulltime", "entry_level", "year_round", "other"
    ]
    source_url: str = Field(description="이 공고를 실제로 확인한 URL. 없으면 이 공고를 만들지 말 것")

    # ── 언어 요건 (사용자 요구사항의 핵심) ──
    language_required: Optional[str] = Field(
        default=None,
        description="예: '일본어 필수(JLPT N2 이상)', '한국어 유창', '영어만으로 가능'. "
                    "페이지에 안 적혀 있으면 null — 절대 추측하지 말 것",
    )
    english_only_ok: Optional[bool] = Field(
        default=None, description="영어만으로 지원·근무 가능한지. 근거 없으면 null"
    )
    requires_japanese: Optional[bool] = Field(
        default=None,
        description="일본어가 **필수**인지. 영어 대체가 가능하면 false. 언급 없으면 null",
    )
    requires_korean: Optional[bool] = Field(
        default=None,
        description="한국어가 **필수**인지. 영어 대체가 가능하면 false. 언급 없으면 null",
    )

    # ── 자격 요건 ──
    grad_year_required: Optional[str] = Field(
        default=None, description="예: '2027年卒', '2027년 2월 졸업예정자'. 없으면 null"
    )
    experience_required: Optional[str] = Field(
        default=None, description="예: '경력 3년 이상', '신입 가능'. 없으면 null"
    )
    visa_sponsorship: Optional[bool] = Field(
        default=None, description="취업비자 스폰서 여부. 명시 안 됐으면 null"
    )
    # ── 외국인 지원 가능 여부: 이 후보자에게 가장 중요한 항목 ──
    foreigner_mentioned: bool = Field(
        default=False,
        description="공고에 외국인/유학생/비자/국적에 대한 언급이 **조금이라도** 있으면 true",
    )
    foreigner_eligible: Optional[bool] = Field(
        default=None,
        description="외국인이 지원 가능한가. true=가능하다고 적혀 있음, "
                    "false=내국인만/비자 불가라고 적혀 있음, null=공고에 언급 없음. "
                    "언급이 없으면 반드시 null 로 둔다 — 추측 금지",
    )
    foreigner_evidence: Optional[str] = Field(
        default=None,
        description="위 판단의 근거가 된 공고 원문 문장. 짧게 그대로 인용. 없으면 null",
    )
    foreigner_target: Optional[
        Literal["domestic_intl_student", "overseas_grad", "any", "unclear"]
    ] = Field(
        default=None,
        description="외국인 채용이 어떤 유형을 대상으로 하는가. "
                    "domestic_intl_student=국내(한국/일본) 대학에 재학·졸업한 유학생 대상 "
                    "(예: '국내 대학 졸업 외국인', '日本の大学卒業'), "
                    "overseas_grad=해외 대학 졸업자 대상 (예: '해외대 졸업자', 'global track'), "
                    "any=출신 대학 무관, unclear=외국인은 뽑는데 대상이 불분명. "
                    "외국인 언급 자체가 없으면 null",
    )
    language_test: Optional[str] = Field(
        default=None,
        description="요구하는 어학시험과 급수를 원문 그대로. "
                    "예: 'TOPIK 4급 이상', 'JLPT N2', '한국어능력시험 5급'. 없으면 null",
    )

    # ── JD 본문 ──
    responsibilities: list[str] = Field(
        default_factory=list,
        description="담당 업무. 원문을 압축하지 말고 그대로 옮긴다. 최대 12개. 없으면 빈 배열",
    )
    qualifications: list[str] = Field(
        default_factory=list,
        description="자격 요건(필수). 원문 그대로, 수치·조건을 빠뜨리지 않는다. 최대 12개",
    )
    preferred: list[str] = Field(
        default_factory=list, description="우대 사항. 원문 그대로. 최대 10개"
    )
    software: list[str] = Field(
        default_factory=list,
        description="요구/우대 소프트웨어 (Revit, Rhino, AutoCAD, 3ds Max 등). 공고에 적힌 것만",
    )
    salary: Optional[str] = Field(default=None, description="급여. 원문 표기 그대로. 없으면 null")
    employment_type: Optional[str] = Field(
        default=None, description="정규직/계약직/인턴 등 고용형태. 없으면 null"
    )
    process: Optional[str] = Field(
        default=None, description="전형 절차 (예: 서류→실기→면접). 없으면 null"
    )

    # ── 연락처: "문의 필요" 로 판정되면 여기가 없으면 아무것도 못 한다 ──
    contact_email: Optional[str] = Field(
        default=None, description="지원·문의용 이메일. 페이지에 있는 것만. 없으면 null"
    )
    contact_phone: Optional[str] = Field(
        default=None, description="채용 문의 전화번호. 페이지에 있는 것만. 없으면 null"
    )
    apply_how: Optional[str] = Field(
        default=None,
        description="지원 방법 원문 (예: '이력서·포트폴리오를 아래 메일로 송부'). 없으면 null",
    )
    firm_projects: list[str] = Field(
        default_factory=list,
        description="페이지에 언급된 **이 사무소의 실제 프로젝트명**. 페이지에 나온 것만. "
                    "네가 아는 지식으로 채우지 마라. 최대 8개. 없으면 빈 배열",
    )

    deadline: Optional[str] = Field(default=None, description="YYYY-MM-DD 또는 원문 표기")
    posted_at: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    location: Optional[str] = None
    summary: str = Field(description="2~3문장. 지원자가 판단할 수 있을 만큼만")

    confidence: Confidence = Field(
        description="confirmed=공식 채용페이지에서 직접 확인 / "
                    "likely=간접 출처 / unverified=추정. 추정이면 절대 confirmed 쓰지 말 것"
    )
    notes: Optional[str] = Field(
        default=None, description="확인 못 한 항목을 여기 적는다. 예: '연봉 미기재, 비자 언급 없음'"
    )


class OfficeReport(BaseModel):
    """오피스 1개에 대한 워커 1개의 결과."""

    office_id: str
    checked_at: str = Field(description="YYYY-MM-DD")
    careers_url_found: Optional[str] = Field(
        default=None, description="실제로 동작하는 채용 페이지 URL. 못 찾았으면 null"
    )
    is_hiring: Optional[bool] = Field(
        default=None, description="신입/인턴 채용이 열려 있는지. 판단 불가면 null"
    )
    postings: list[Posting] = Field(
        default_factory=list, description="찾은 공고. 없으면 빈 배열. 지어내지 말 것"
    )
    unresolved: list[str] = Field(
        default_factory=list,
        description="확인하려 했으나 못 밝힌 것들. 예: '서울오피스 신입 채용 여부 — 페이지에 언급 없음'",
    )
