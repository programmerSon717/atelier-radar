"""공고가 이 후보자에게 현실적인지 표시한다. 거르지는 않는다 (B안).

추측은 하지 않는다. 공고에 실제로 적힌 것만 근거로 쓴다.
"회사가 작아 보이니 비자를 안 해줄 것이다" 같은 판단은 하지 않는다 —
대신 "지방 소재", "시공사", "설계직 아님" 처럼 확인 가능한 사실만 붙인다.
"""
import re

# 설계직이 아닌 것들. 잡보드 검색에는 이런 게 잔뜩 섞여 들어온다.
NOT_DESIGN = re.compile(
    r"현장\s*관리|현장\s*소장|공무|시공\s*관리|감리|안전\s*관리|품질\s*관리|"
    r"기술\s*영업|영업직|자재|적산|견적|측량|토목|설비\s*시공|전기\s*시공|"
    r"CAD\s*오퍼레이터|캐드\s*원|모델링\s*알바", re.I)
# "도면 작업" 은 뺐다 — 그건 설계직이 하는 일이지 배제 사유가 아니다.

# 회사명에서 시공사를 알아보는 말
CONSTRUCTOR = re.compile(r"종합건설|건설\(주\)|건설㈜|建設|construction", re.I)

# 수도권 (외국인이 실제로 정착·통근 가능한 범위)
CAPITAL_AREA = re.compile(r"서울|인천|경기|고양|성남|수원|용인|부천|안양|과천|김포|하남|광명")
KR_REGION = re.compile(r"강원|충북|충남|전북|전남|경북|경남|대전|대구|광주|울산|부산|제주|세종")

# 외국인 지원이 실제로 열려 있다는 신호 (공고에 적혀 있을 때만)
FOREIGN_OK = re.compile(
    r"외국인|비자|영주권|E-?7|글로벌|해외\s*프로젝트|영어\s*가능|bilingual|"
    r"visa|sponsor|foreign|international|外国人|留学生|外籍", re.I)


def label(posting, office) -> list[str]:
    """공고에 붙일 현실성 라벨. 근거 없으면 아무것도 붙이지 않는다."""
    out: list[str] = []
    # 직무 판정은 제목·회사명으로만 한다. 모델이 쓴 summary 산문에 대고 맞추면
    # "실시설계 도면 작업" 같은 정상 공고가 걸린다.
    blob = " ".join(filter(None, [posting.title, posting.company, posting.location]))
    # notes 는 "무엇을 확인 못 했는지" 적는 칸이다. "비자 정보 없음" 같은 부정문이 들어 있어서
    # 여기서 '비자' 를 찾으면 정반대로 읽게 된다. 그래서 notes 는 신호 탐지에서 제외한다.
    jd_blob = " ".join(filter(None, [
        posting.language_required, posting.employment_type,
        *posting.qualifications, *posting.preferred, *posting.responsibilities,
    ]))

    m = NOT_DESIGN.search(blob)
    if m:
        out.append(f"🔧 설계직 아님 — {m.group(0).strip()}")

    if posting.company and CONSTRUCTOR.search(posting.company):
        out.append("🏗 시공사 (설계사무소 아님)")

    loc = posting.location or ""
    if office.country == "KR" and loc:
        if KR_REGION.search(loc) and not CAPITAL_AREA.search(loc):
            out.append(f"📍 지방 소재 — {loc}")

    # summary 에도 "비자 스폰서 여부는 언급되지 않음" 같은 부정문이 들어간다.
    # notes 와 같은 이유로 제외하고, 공고 원문에서 온 필드만 본다.
    fm = FOREIGN_OK.search(jd_blob) or FOREIGN_OK.search(posting.title or "")
    if fm:
        out.append(f"🌏 외국인 지원 관련 언급 — {fm.group(0)}")

    return out


def is_low_fit(labels: list[str]) -> bool:
    """설계직이 아니거나 시공사면 우선순위를 낮춘다."""
    return any(l.startswith(("🔧", "🏗")) for l in labels)


# ── 사무소 수준 판정 ───────────────────────────────────────────────
# 후보자는 Brown 학부 + Columbia GSAPP M.Arch 다. 설계 역량을 쌓을 수 없는 곳에
# 보내는 건 시간 낭비다. 다만 "작아 보인다" 같은 인상으로 자르지 않는다 —
# 공고에서 확인할 수 있는 사실만 근거로 쓴다.

# 설계 사무소로서 최소한의 신호 (하나라도 있으면 통과)
GOOD_SIGNAL = re.compile(
    r"수상|공모|당선|현상설계|국제\s*설계|해외\s*프로젝트|출판|전시|"
    r"포트폴리오\s*심사|실기\s*시험|BIM|Rhino|Revit|Grasshopper|친환경|"
    r"미술관|박물관|문화시설|공공건축|마스터플랜|도시설계|"
    r"受賞|コンペ|国際|美術館|博物館|"
    r"競圖|得獎|美術館|博物館|"
    r"award|competition|international|museum|cultural|master ?plan", re.I)

# 설계보다 인허가·도면 대행에 가까운 곳의 신호
LOW_SIGNAL = re.compile(
    r"인허가\s*대행|허가\s*방|도면\s*대행|캐드\s*대행|단기\s*아르바이트|"
    r"아르바이트|알바|파트타임|일용|초대졸|고졸", re.I)


def firm_grade(posting, office) -> tuple[str, str]:
    """('good'|'plain'|'weak', 이유). 공고에서 읽히는 것만 근거로 삼는다."""
    # 우리가 직접 고른 타겟(대형·아틀리에·글로벌)은 이미 검증된 곳이다
    if office.tier in ("large", "global", "atelier", "mid"):
        return "good", f"추적 대상 사무소 ({office.tier})"

    blob = " ".join(filter(None, [
        posting.title, posting.company, posting.summary,
        *(posting.qualifications or []), *(posting.preferred or []),
        *(posting.responsibilities or []), *(posting.software or []),
    ]))
    m = LOW_SIGNAL.search(blob)
    if m:
        return "weak", f"설계 실무와 거리가 있음 — {m.group(0).strip()}"
    g = GOOD_SIGNAL.search(blob)
    if g:
        return "good", f"설계 역량 신호 — {g.group(0).strip()}"
    return "plain", "설계사무소로 보이나 규모·성격을 판단할 근거가 공고에 없음"
