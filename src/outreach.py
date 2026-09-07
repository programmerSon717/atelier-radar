"""문의 메일 초안을 만든다.

'문의 필요' 라고만 알려주면 지원자가 할 수 있는 게 없다.
어디로 물어보는지(연락처), 무슨 얘기를 꺼낼지(그 사무소가 실제로 한 프로젝트),
그리고 본인 이력의 무엇과 엮을지까지 같이 줘야 실제로 메일이 나간다.

지어내지 않는 것은 여기서도 같다. 프로젝트는 페이지에서 실제로 읽은 것만 쓴다.
"""
import os
from typing import Any, Optional

from pydantic import BaseModel, Field

from .models import Posting


class Outreach(BaseModel):
    subject: str = Field(description="메일 제목. 회사·직무를 명확히. 한 줄")
    body: str = Field(
        description="메일 본문 전체. 바로 복사해서 보낼 수 있는 완성된 글. "
                    "인사 → 자기소개 한 줄 → 이 사무소에 관심을 갖게 된 구체적 이유 → "
                    "묻고 싶은 것(외국인 지원 가능 여부·비자 스폰서·어학 요건) → "
                    "첨부 안내 → 맺음말. 과장하거나 없는 경력을 쓰지 마라."
    )
    hooks: list[str] = Field(
        default_factory=list,
        description="이 사무소와 지원자를 잇는 접점. 각 항목은 '사무소의 무엇 ↔ 지원자의 무엇' 형태. "
                    "페이지에서 확인한 사실만. 최대 4개",
    )
    ask_points: list[str] = Field(
        default_factory=list,
        description="반드시 물어봐야 할 것들. 최대 4개",
    )


SYSTEM = """\
너는 건축 전공 구직자의 문의 메일을 대신 써 준다.

지켜야 할 것:
1. **없는 사실을 쓰지 마라.** 지원자 이력은 아래 준 것만, 사무소 프로젝트는 아래 준 목록만 쓴다.
   프로젝트 목록이 비어 있으면 프로젝트 얘기를 아예 하지 마라. 지어내면 그 메일은 못 쓴다.
2. 과장하지 마라. 경력 0년이면 0년인 채로 쓴다. "열정" 같은 상투어 대신 구체적인 것으로 채운다.
3. 짧게. 채용 담당자는 오래 안 읽는다. 본문 250~350자 안쪽.
4. 핵심 질문(외국인 지원 가능 여부·비자 스폰서·어학 요건)을 반드시 넣되, 따지듯 묻지 말고
   "확인하고 지원하고 싶다" 는 태도로 쓴다.
5. 메일 언어는 그 사무소가 있는 나라의 언어로 쓴다 (한국=한국어, 일본=일본어, 대만=번체 중문).
   단 영어가 공용어라고 공고에 적혀 있으면 영어로 쓴다.
"""

USER = """\
## 보내는 사람 (지원자)
- 이름: {name}
- 대만 국적, 현재 미국 거주
- 미국 대학원 M.Arch 2027년 5월 졸업 예정 (학부도 미국, 건축)
- 정규직 경력 0년. 인턴 2회 — 전시·뮤지엄 디자인 스튜디오, 건축 스튜디오
- 언어: 영어 능통, 중국어 원어민, 한국어 초급(학습 중), 일본어 불가
- 다룰 수 있는 툴: Rhino, Revit, Blender, V-Ray, Enscape, Photoshop, Illustrator,
  InDesign, ClimateStudio, 3D 프린팅/레이저커팅
- 강점: 전시·뮤지엄 공간 설계 실무 경험, 환경·지속가능성 분석(ClimateStudio),
  수상·출판·전시 이력, 중화권 프로젝트에 언어 강점

## 받는 곳
- 사무소: {firm}
- 나라: {country}
- 공고: {title} ({track})
- 연락처: {contact}
- 지원 방법 원문: {apply_how}

## 이 사무소의 프로젝트 (페이지에서 확인된 것만)
{projects}

## 이 공고에서 확인된 것
- 자격 요건: {quals}
- 요구 툴: {software}
- 언어 요건: {lang}
- 확인 안 된 것: {unknowns}

위 정보만 가지고 문의 메일을 써라. 프로젝트 목록이 비어 있으면 프로젝트를 언급하지 마라.
서명에는 위에 준 이름을 그대로 쓴다.
"""


def build_prompt(p: Posting, firm: str, country: str, unknowns: list[str]) -> str:
    contact = " / ".join(filter(None, [p.contact_email, p.contact_phone])) or "페이지에 없음"
    projects = "\n".join(f"- {x}" for x in p.firm_projects) or "(페이지에서 확인된 프로젝트 없음)"
    # 이름은 저장소에 두지 않는다 (공개 저장소다). 환경변수로만 들어온다.
    name = os.environ.get("CANDIDATE_NAME") or "(지원자 본인 이름을 쓸 자리)"
    return USER.format(
        name=name,
        firm=firm, country={"KR": "한국", "JP": "일본", "TW": "대만"}.get(country, country),
        title=p.title, track=p.track, contact=contact,
        apply_how=p.apply_how or "명시 없음",
        projects=projects,
        quals=" / ".join(p.qualifications[:6]) or "명시 없음",
        software=" · ".join(p.software[:8]) or "명시 없음",
        lang=p.language_required or "명시 없음",
        unknowns=" / ".join(unknowns[:4]) or "없음",
    )


def draft(client, p: Posting, firm: str, country: str,
          unknowns: list[str], cfg: dict[str, Any]) -> Optional[Outreach]:
    """실패하면 None. 메일 초안이 없다고 공고 알림이 막히면 안 된다."""
    from google.genai import types

    from .extract import _models

    for model_name in _models(cfg):
        try:
            r = client.models.generate_content(
                model=model_name,
                contents=build_prompt(p, firm, country, unknowns),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    response_mime_type="application/json",
                    response_schema=Outreach,
                    temperature=0.3,
                ),
            )
            if r.parsed:
                return r.parsed
        except Exception:
            continue
    return None
