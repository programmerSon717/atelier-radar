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

    # ── JD 본문 ──
    responsibilities: list[str] = Field(
        default_factory=list,
        description="담당 업무. 공고에 적힌 것만, 각 항목 한 줄로. 최대 6개. 없으면 빈 배열",
    )
    qualifications: list[str] = Field(
        default_factory=list,
        description="자격 요건(필수). 공고에 적힌 것만. 최대 6개",
    )
    preferred: list[str] = Field(
        default_factory=list, description="우대 사항. 공고에 적힌 것만. 최대 5개"
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
