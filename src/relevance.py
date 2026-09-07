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
    r"CAD\s*오퍼레이터|캐드\s*원|모델링\s*알바|"
    # 일본어 — 営業職 이 설계직으로 통과하고 있었다 (NOMURA 4건)
    r"営業職|営業担当|施工管理|現場監督|積算|購買|人事職|経理職|"
    # 번체 중문 — 日文의 業務(=업무)와 겹치므로 반드시 직무명 통째로만 잡는다
    r"業務專員|業務助理|工地主任|監造|估價|繪圖員|"
    r"sales|estimat|site\s*supervis|procurement", re.I)
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
    nd = no_degree_required(posting)
    if nd:
        out.append(f"🎓 공고에 학력 조건 없음 — {nd}")

    fm = FOREIGN_OK.search(jd_blob) or FOREIGN_OK.search(posting.title or "")
    if fm:
        out.append(f"🌏 외국인 지원 관련 언급 — {fm.group(0)}")

    return out


def is_low_fit(labels: list[str]) -> bool:
    """설계직이 아니거나 시공사면 우선순위를 낮춘다."""
    return any(l.startswith(("🔧", "🏗")) for l in labels)


# ── 사무소 수준 판정 ───────────────────────────────────────────────
# 후보자는 미국 상위권 대학원의 건축학 석사 과정에 있다. 설계 역량을 쌓을 수 없는 곳에
# 보내는 건 시간 낭비다. 다만 "작아 보인다" 같은 인상으로 자르지 않는다 —
# 공고에서 확인할 수 있는 사실만 근거로 쓴다.
# (학교 이름은 여기 적지 않는다. 공개 저장소다.)

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


# 학력을 아예 안 보는 자리는 건축 석사가 갈 자리가 아니다.
# 도면 대행·시공 보조·단순 모델링 인력 모집이 대부분이라 실무 경력으로 쌓이지 않는다.
NO_DEGREE = re.compile(
    r"학력\s*무관|학력\s*불문|학력\s*무제한|학력\s*제한\s*없|"
    r"學歷不拘|學歷不限|不限學歷|学歴不問|学歴不定", re.I)


# 우리가 직접 고르고 확인한 사무소들. 여기는 게시판 표기만으로 자르지 않는다.
VERIFIED_TIERS = ("atelier", "large", "global", "mid")


def drop_for_no_degree(posting, office) -> str | None:
    """이 공고를 '학력무관' 을 이유로 버릴 것인가.

    vmspace·사람인은 채용 폼의 학력 칸에 '학력무관' 을 그냥 넣는 관행이 있다.
    실제로 원오원아키텍스(아틀리에) 신입공채도 그렇게 찍혀 있었다. 표기만 보고 자르면
    우리가 직접 고른 사무소가 통째로 사라진다. 그래서 **이름 모를 곳에만** 적용한다.
    검증된 사무소는 버리지 않고 라벨로만 알린다."""
    nd = no_degree_required(posting)
    if not nd:
        return None
    if office is not None and office.tier in VERIFIED_TIERS:
        return None
    # 잡보드로 들어온 공고는 office 가 게시판이다. 회사 이름으로 우리 목록과 맞춰본다.
    from .targets import match_office
    known = match_office(getattr(posting, "company", None), posting.title)
    if known is not None and known.tier in VERIFIED_TIERS:
        return None
    return nd


def no_degree_required(posting) -> str | None:
    """'학력무관' 이라고 적힌 공고인가. 적혀 있으면 그 원문을 돌려준다.

    모델이 쓴 summary·notes 는 보지 않는다. "학력 조건은 언급되지 않음" 같은
    부정문이 들어 있어서 정반대로 읽게 된다 (label() 의 notes 제외와 같은 이유)."""
    blob = " ".join(filter(None, [
        posting.education_required, posting.employment_type,
        *(posting.qualifications or []), *(posting.preferred or []),
    ]))
    m = NO_DEGREE.search(blob)
    return m.group(0).strip() if m else None


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


# ── 지원 추천도 ────────────────────────────────────────────────
# 사무소 수준(firm_grade)만으로는 "이 사람이 갈 만한가" 가 안 나온다.
# 포트폴리오에 실제로 들어 있는 작업과 공고가 겹치는지까지 봐야 한다.
#
# 포트폴리오(2024~2025)에서 확인된 작업 갈래:
#   · 문화·전시·종교 시설 (문화보존센터, 수도원 증축)
#   · 집합주거·복합용도 (East Village 협동주거)
#   · 도시·조경·공공공간 (City Hall 공원, 마스터플랜 50/50 전략)
#   · 모듈러·순환건축 (인턴 실무 — kit-of-parts 가구 시스템)
#   · 리서치 기반 설계 (전쟁 피해 매핑, 카토그래피)
#   · 시각화·물리모형·다이어그램 (Rhino, V-Ray, Enscape, 모형 제작)
# 반대로 실무 경험이 없는 것: 인허가, 시공, 감리, AutoCAD 도면 대행, 대형 상업 타워.

PORTFOLIO = {
    "문화·전시": re.compile(
        r"미술관|박물관|전시|문화\s*시설|공연|도서관|기념관|종교|성당|사찰|"
        r"美術館|博物館|展示|文化施設|劇場|"
        r"文化中心|展覽|文資|"
        r"museum|gallery|exhibit|cultur|library|theat|religio", re.I),
    "주거·복합": re.compile(
        r"주거|공동\s*주택|아파트|주상복합|집합\s*주거|생활숙박|기숙사|"
        r"住宅|集合住宅|マンション|"
        r"住宅|集合住宅|"
        r"housing|residential|mixed[- ]?use|apartment", re.I),
    "도시·조경": re.compile(
        r"도시\s*설계|마스터\s*플랜|조경|공원|공공\s*건축|광장|재생|"
        r"都市|ランドスケープ|公園|"
        r"都市設計|景觀|公共|"
        r"urban|landscape|master\s?plan|public\s*space|regenerat", re.I),
    "모듈러·지속가능": re.compile(
        r"모듈러|프리팹|친환경|지속\s*가능|탄소|패시브|에너지|녹색|리모델링|"
        r"環境|省エネ|木造|"
        r"永續|綠建築|循環|"
        r"modular|prefab|sustainab|passive|carbon|LEED|green\s*build|circular", re.I),
    "리서치·공모": re.compile(
        r"리서치|연구|현상\s*설계|공모|당선|기획\s*설계|컨셉\s*설계|"
        r"コンペ|設計競技|"
        r"競圖|"
        r"research|competition|concept\s*design", re.I),
    "시각화·모형": re.compile(
        r"렌더링|모형|다이어그램|시각화|비주얼|투시도|"
        r"Rhino|V-?Ray|Enscape|Blender|Photoshop|InDesign|"
        r"レンダリング|模型|"
        r"渲染|"
        r"rendering|visuali[sz]|diagram|model\s?making", re.I),
}

FIT_GRADES = ("recommend", "neutral", "avoid")


def portfolio_overlap(posting) -> list[str]:
    """공고와 포트폴리오가 겹치는 갈래. 공고 원문에서 온 필드만 본다."""
    blob = " ".join(filter(None, [
        posting.title, posting.company,
        *(posting.responsibilities or []), *(posting.qualifications or []),
        *(posting.preferred or []), *(posting.software or []),
    ]))
    return [k for k, rx in PORTFOLIO.items() if rx.search(blob)]


def fit_grade(posting, office, assessment, labels: list[str] | None = None
              ) -> tuple[str, list[str]]:
    """('recommend'|'neutral'|'avoid', 근거들).

    학력이 아니라 **작업 내용**으로 가른다. 근거 없이 좋게도 나쁘게도 쓰지 않는다."""
    # assess() 는 마지막에 a.labels 를 판정 문구로 덮어쓴다. 그래서 여기 넘어온
    # labels 에는 🔧/🏗 가 이미 없다 — 원본을 직접 다시 만들어 쓴다.
    labels = labels if labels is not None else label(posting, office)
    reasons: list[str] = []

    grade_firm, why_firm = firm_grade(posting, office)
    overlap = portfolio_overlap(posting)

    # ── 비추천: 가서 설계를 못 배우거나, 지금 지원해도 안 되는 자리 ──
    if grade_firm == "weak":
        return "avoid", [why_firm]
    if is_low_fit(labels) or "직무 적합성 낮음" in getattr(assessment, "soft_blockers", []):
        bad = [l for l in labels if l.startswith(("🔧", "🏗"))]
        return "avoid", bad or ["설계직으로 보기 어려움"]
    if assessment.blockers:
        return "avoid", [f"지원 자체가 막힘 — {b}" for b in assessment.blockers]

    # ── 추천: 검증된 사무소 + 포트폴리오와 겹치는 작업 ──
    strong_firm = (office.tier in ("large", "global", "atelier")) or grade_firm == "good"
    if strong_firm:
        reasons.append(why_firm)
    if overlap:
        reasons.append("포트폴리오와 겹침 — " + " · ".join(overlap))
    if office.eng_ok in ("yes", "partial") or any(l.startswith("🌏") for l in labels):
        reasons.append("외국인·영어 관련 신호 있음")

    if strong_firm and overlap:
        return "recommend", reasons
    if strong_firm and office.priority == "high":
        return "recommend", reasons + ["우선 추적 대상 사무소"]
    return "neutral", reasons or ["판단할 근거가 공고에 부족함"]
