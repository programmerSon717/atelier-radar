"""문의 메일 초안을 만든다.

'문의 필요' 라고만 알려주면 지원자가 할 수 있는 게 없다.
어디로 물어보는지(연락처), 무슨 얘기를 꺼낼지(그 사무소가 실제로 한 프로젝트),
그리고 본인 이력의 무엇과 엮을지까지 같이 줘야 실제로 메일이 나간다.

지어내지 않는 것은 여기서도 같다. 프로젝트는 페이지에서 실제로 읽은 것만 쓴다.
"""
import os
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from .models import Posting


class Outreach(BaseModel):
    subject: str = Field(description="메일 제목. 회사·직무를 명확히. 한 줄")
    body: str = Field(
        description="메일 본문 전체. 바로 복사해서 보낼 수 있는 완성된 글. "
                    "바로 복사해서 보낼 수 있게 **문단을 빈 줄로 나눠서** 쓴다. "
                    "한 덩어리로 붙여 쓰면 읽히지 않는다. 과장하거나 없는 경력을 쓰지 마라."
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


# ── 회사명 다듬기 ─────────────────────────────────────────────
# 메일 본문에 "(주)플랜엠" 이라고 쓰는 사람은 없다. 법인격 표기는 등기부에나 쓴다.
# 다만 일본어의 株式会社 는 메일에서도 정상 표기라 남긴다 (현지 관행).
CORP_ANY = re.compile(
    r"\(\s*주\s*\)|（\s*주\s*）|㈜|주식\s*회사|\(\s*유\s*\)|유한\s*회사|"
    r"股份有限公司|有限公司|"
    r"Co\.?,?\s*Ltd\.?|Inc\.?$|LLC|L\.L\.C\.", re.I)


def natural_name(name: str, country: str = "KR") -> str:
    """사람이 부르는 이름으로 바꾼다. '(주)플랜엠' → '플랜엠'."""
    out = CORP_ANY.sub(" ", name or "")
    out = re.sub(r"[\s,]{2,}", " ", out).strip(" ,·-")
    return out or (name or "").strip()


SYSTEM = """\
너는 건축 전공 구직자를 대신해 사무소에 보낼 메일을 쓴다.
**받는 사람은 그 사무소에서 일하는 사람이다.** 사람이 사람에게 쓰는 글을 써라.

## 절대 쓰지 마라 (이렇게 쓰면 그 메일은 버려진다)
- **"프로젝트 목록이 별도로 기재되어 있지 않으나", "확인되지 않았지만",
  "정보가 부족하나", "공고를 통해 ~라는 인상을 받아"** — 이런 문장은 쓰지 마라.
  자료를 못 찾았다는 사정은 **읽는 사람과 아무 상관이 없다.** 아는 것만 쓰고 나머지는 침묵해라.
  아는 게 정말 없으면 그 사무소가 하는 일 자체를 한 문장으로 말해라.
- **법인격 표기.** "(주)", "㈜", "주식회사"(단 일본어 메일은 예외), "股份有限公司".
  아래 준 이름을 그대로 쓴다. 멋대로 (주)를 붙이지 마라.
- "귀사의 무궁한 발전", "열정을 가지고", "성실히 임하겠습니다" 같은 상투어.
- **뉴스 제목의 기사체 표기를 그대로 옮기지 마라.** 신문은 자리를 아끼려고 "美·韓·日",
  "착수", "본격화" 처럼 쓴다. 메일에서는 "미국", "일본" 처럼 말하듯 풀어 쓴다.
- 사실을 옮길 때 **시기를 바꾸지 마라.** 석사 과정에서 한 작업을 "학부 시절" 이라고 쓰면
  그건 틀린 말이다. 확실하지 않으면 시기를 아예 말하지 마라.
- 없는 사실. 아래 준 것 말고는 한 글자도 지어내지 마라.

## 본문 순서 — 반드시 이대로
① **그 사무소에서 본 것부터 시작한다.** 프로젝트나 뉴스에서 확인된 구체적인 것을
   이름으로 말하고, 그게 왜 눈에 들어왔는지 **본인 작업과 엮어서** 쓴다.
   자기소개보다 이게 먼저다. 여기가 이 메일의 전부다.
② 그래서 이 사무소에서 일하고 싶던 차에 **마침 이 공고를 보았다** 고 잇는다.
③ 본인이 누구인지: 건축 석사과정, 졸업 시기, **영어와 중국어가 모두 원어민 수준**이라
   어떤 자리에서 쓸모가 있는지, 다뤄 온 작업과 툴.
④ 그래서 확인하고 싶은 것 — **외국인도 지원할 수 있는지**, 비자, 어학 요건.
   따지듯 묻지 말고 "확인하고 지원하려 한다" 는 태도로.
⑤ 포트폴리오·이력서를 보내겠다는 한 줄과 맺음말.

길이는 400~600자. ①에 가장 많이 쓴다. **①~⑤ 사이는 빈 줄로 문단을 나눈다.**
메일 언어는 그 사무소가 있는 나라 말로 쓴다 (한국=한국어, 일본=일본어, 대만=번체 중문).
공고에 영어가 공용어라고 적혀 있으면 영어로 쓴다.
"""

USER = """\
## 보내는 사람 (지원자)
- 이름: {name}
- 대만 국적. 현재 미국 거주
- {school}에서 건축학 석사과정(M.Arch) 재학 — 2027년 5월 졸업 예정. 학부도 미국에서 건축 전공
- 정규직 경력 0년. 인턴 2회 — 전시·뮤지엄 디자인 스튜디오, 건축 스튜디오(모듈러·순환건축)
- 언어: **중국어 원어민(번체), 영어 원어민 수준**, 한국어 초급, 일본어 불가
- 해 온 작업 (**전부 석사 과정 스튜디오 작업**이다. 학부 작업이라고 쓰지 마라):
  문화·전시 시설, 전후 문화보존센터, 집합주거·복합용도,
  도시·조경(마스터플랜), 모듈러 kit-of-parts 가구 시스템(인턴 실무),
  리서치 기반 설계(피해 매핑·카토그래피), 물리모형·다이어그램·내러티브 드로잉
- 툴: Rhino, Revit, Blender, V-Ray, Enscape, Photoshop, Illustrator, InDesign,
  ClimateStudio(환경분석), 3D 프린팅·레이저커팅

## 받는 곳
- 사무소: {firm}   ← **이 표기를 그대로 쓴다**
- 나라: {country}
- 공고: {title} ({track})
- 연락처: {contact}
- 지원 방법 원문: {apply_how}

## 이 사무소에 대해 확인된 것
### 채용페이지에서 읽은 프로젝트
{projects}

### 뉴스에서 확인된 것 (제목에 적힌 사실만. 부풀리지 마라)
{news}

## 이 공고에서 확인된 것
- 자격 요건: {quals}
- 요구 툴: {software}
- 언어 요건: {lang}
- 확인 안 된 것: {unknowns}

위 재료로 메일을 써라. **①에 쓸 구체적인 것을 위에서 반드시 하나 이상 골라 이름으로 언급하고,**
지원자가 해 온 작업 중 그것과 닿는 것을 짚어라. 둘 다 정말 없을 때만 그 사무소의 분야를
한 문장으로 말하고 넘어간다 — **없다는 말 자체를 문장으로 쓰지는 마라.**
서명에는 위에 준 이름을 그대로 쓴다.
"""


def build_prompt(p: Posting, firm: str, country: str, unknowns: list[str],
                 news_items: Optional[list[dict]] = None) -> str:
    contact = " / ".join(filter(None, [p.contact_email, p.contact_phone])) or "페이지에 없음"
    projects = "\n".join(f"- {x}" for x in p.firm_projects) or "(없음 — 뉴스 쪽을 써라)"
    news = "\n".join(
        f"- {n['title']}" + (f" ({n['source']}, {n['date']})" if n.get('source') else "")
        for n in (news_items or [])
    ) or "(없음)"
    # 이름·학교는 저장소에 두지 않는다 (공개 저장소다). 환경변수로만 들어온다.
    name = os.environ.get("CANDIDATE_NAME") or "(지원자 본인 이름을 쓸 자리)"
    school = os.environ.get("CANDIDATE_SCHOOL") or "미국 대학원"
    return USER.format(
        name=name, school=school,
        firm=natural_name(firm, country),
        country={"KR": "한국", "JP": "일본", "TW": "대만"}.get(country, country),
        title=p.title, track=p.track, contact=contact,
        apply_how=p.apply_how or "명시 없음",
        projects=projects, news=news,
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

    # 채용페이지에 프로젝트가 없으면 뉴스에서 찾아온다.
    # "프로젝트 목록이 기재되어 있지 않으나" 로 시작하는 메일을 보내지 않기 위한 것이다.
    news_items: list[dict] = []
    if not p.firm_projects and cfg.get("outreach", {}).get("news_lookup", True):
        from . import news as _news
        news_items = _news.headlines(natural_name(firm, country), country,
                                     limit=cfg.get("outreach", {}).get("news_limit", 5))

    prompt = build_prompt(p, firm, country, unknowns, news_items)
    for model_name in _models(cfg):
        try:
            r = client.models.generate_content(
                model=model_name,
                contents=prompt,
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
