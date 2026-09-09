"""공고 내용을 한국어·영어·번체중문 세 벌로 만든다.

공고는 일본어·중국어·영어로 올라온다. 그대로 두면 읽을 수 없고, 기계적으로 옮기면
"応募" 가 "응모" 로 나온다. 그래서 **뜻이 통하게 옮긴다** — 다만 지어내지는 않는다.
없는 항목은 비운 채로 둔다. 항목 수를 줄이지도 않는다.

한 번의 호출로 세 언어를 다 만든다. 따로 부르면 용어가 갈린다.
"""
import hashlib
import json
import re
from typing import Any, Optional

FIELDS_TEXT = ("title", "company", "summary", "location", "employment_type", "process",
               "apply_how", "language_required", "salary", "notes", "gate_label",
               "gate_reason", "gate_evidence", "gate_action", "pay_note",
               # 화면에 그대로 찍히는데 옮기지 않아 원문이 새던 자리들.
               # deadline 은 날짜 계산용 원본이라 못 건드린다 — 표시용을 따로 둔다.
               "pay_stated", "deadline_text",
               "mail_subject", "mail_body")
FIELDS_LIST = ("responsibilities", "qualifications", "preferred", "firm_projects",
               "blockers_desc", "soft_desc", "met", "unknowns", "fit_why",
               # "스케치업 · 라이노 · 인디자인" 이 그대로 나가고 있었다
               "software",
               "mail_hooks", "mail_asks")

LANGS = ("ko", "en", "zh_TW")

# 되풀이되는 말은 미리 못 박는다. 공고마다 다르게 옮기면 목록이 읽히지 않는다.
GLOSSARY = """\
| 한국어 | English | 繁體中文 |
|---|---|---|
| 지원 가능 | Open to foreign applicants | 開放外籍應徵 |
| 문의 필요 | Needs confirmation | 需要詢問確認 |
| 국내 대학 졸업·유학생 전형 — 해당 없음 | Domestic-degree / international-student track — not eligible | 限當地大學畢業·留學生 — 不符資格 |
| 어학시험·현지어 요구 | Local-language test required | 需要當地語言檢定 |
| 지원 불가 | Not open to foreign applicants | 不開放外籍應徵 |
| 추천 | Recommended | 推薦 |
| 중립 | Neutral | 中立 |
| 비추천 | Not recommended | 不推薦 |
| 신입공채 | New-graduate hiring | 新鮮人招募 |
| 전환형 인턴 | Internship with conversion to full-time | 可轉正實習 |
| 상시채용 | Year-round hiring | 常年招募 |
| 마감 | Deadline | 截止 |
| 담당 업무 | Responsibilities | 工作內容 |
| 자격 요건 | Requirements | 應徵資格 |
| 우대 사항 | Preferred | 加分條件 |
| 경력 0년 | No full-time experience | 無正職經驗 |
| 회사 전체 평균 | Company-wide average | 公司整體平均 |
| 신입 가능 | Open to new graduates | 開放新鮮人 |
| 언어 요건 미기재 | Language requirement not stated | 公告未載明語言要求 |
| 졸업연도 조건 | Graduation-year requirement | 畢業年度條件 |
| 경력 N년 요구 | Requires N years of experience | 要求 N 年經驗 |
| 경력 N년 이하 대상 | Open to those with N years of experience or less | 對象為經驗 N 年以下者 |
| 제2신졸 | Recent graduates within a few years of entering work (dai-ni shinsotsu) | 第二新卒 |
| 학업 연차 조건 | Academic-year requirement | 修業年限條件 |
| 포트폴리오와 겹침 | Overlaps with the portfolio | 與作品集重疊 |
| 추적 대상 사무소 | Tracked office | 追蹤中的事務所 |
| 판단할 근거가 공고에 부족함 | The posting gives too little to judge | 公告資訊不足，難以判斷 |
| 외국인·영어 관련 신호 있음 | Mentions foreign applicants or English | 有外籍·英語相關訊號 |
| 지원 자체가 막힘 | Blocked from applying | 無法應徵 |
| 비자 스폰서 없음 — 본인이 해결해야 함 | No visa sponsorship — you must arrange it yourself | 不提供簽證贊助 — 需自行處理 |
| 미검증 — 출처를 직접 확인할 것 | Unverified — check the source yourself | 未驗證 — 請自行確認出處 |
| 이미 마감됨 | Already closed | 已截止 |
| 문화·전시 | Culture & exhibition | 文化·展覽 |
| 주거·복합 | Housing & mixed-use | 住宅·複合 |
| 도시·조경 | Urban & landscape | 都市·景觀 |
| 모듈러·지속가능 | Modular & sustainability | 模組化·永續 |
| 리서치·공모 | Research & competitions | 研究·競圖 |
| 시각화·모형 | Visualisation & models | 視覺化·模型 |
| 스케치업 | SketchUp | SketchUp |
| 라이노 | Rhino | Rhino |
| 인디자인 | InDesign | InDesign |
| 상시채용 | Year-round | 常年招募 |
"""

SYSTEM = """\
너는 건축 채용공고를 세 언어로 옮긴다. 한국어(ko), 영어(en), 번체중문(zh_TW).

지켜야 할 것:
1. **원문에 없는 것을 만들지 마라.** 항목을 늘리지도 줄이지도 않는다.
   리스트는 **들어온 개수와 순서를 그대로** 지킨다.
2. 직역하지 마라. 그 나라 채용공고가 실제로 쓰는 말로 옮긴다.
   영어는 미국 건축사무소 채용공고 문체, 번체중문은 대만 사무소 공고 문체로 쓴다.
   "応募" 를 "응모" 라고 옮기는 식의 기계적 번역은 하지 마라 — "지원" 이다.
3. **회사명(company)은 그 언어권에서 통용되는 표기로 적는다.** 영어면 로마자 표기
   (예: "(주)엔씨티엔지니어링종합건축사사무소" → "NCT Engineering Architects"),
   번체중문이면 한자 표기. 통용 표기를 모르면 원문을 그대로 두고 지어내지 마라.
   프로젝트명·역명·상 이름 같은 다른 고유명사는 **원문 표기 그대로** 둔다.
   다만 **주소·도시는 읽는 사람 말로 옮긴다** — "서울 마포구" 는 영어로 Mapo-gu, Seoul,
   번체중문으로 首爾 麻浦區 다. 번지·건물명은 원문을 살린다.
   한글 음을 지어서 붙이지 마라 — "大林組" 를 "오바마구미" 라고 쓴 적이 있다. 확실하지
   않으면 원문만 둔다.
4. 자격 요건의 **수치·기간·급수·연도는 절대 바꾸지 마라** (TOEIC 700, N2, 2027년 2월 등).
   **조건의 방향도 바꾸지 마라.** "경력 3년 이하 대상" 은 3년 넘으면 안 된다는 뜻이지
   3년을 요구한다는 뜻이 아니다. 뒤집으면 지원할 수 있는 자리를 잃는다.
5. mail_subject / mail_body 는 **읽으라고** 옮기는 것이다. 실제로 보낼 때는 원문을
   그대로 보낸다 (한국 사무소에는 한국어로 보내야 하니까). 그러니 자연스럽게 옮기되
   내용을 바꾸지 마라.
6. **출력에 원문 언어가 남아 있으면 안 된다.** en 은 전부 영어로, zh_TW 는 전부
   번체중문으로 쓴다. "언어 요건 미기재" 같은 조각을 그대로 두지 마라.
   **공고에서 따온 인용문도 옮긴다.** "신입 가능 — 正社員としての就業経験のない方" 처럼
   대시 뒤에 원문을 붙여 둔 자리가 많은데, 그 뒷부분까지 전부 옮겨야 한다.
   회사명·프로젝트명만 예외다.
   gate_evidence 는 "이렇게 적혀 있어서 그렇게 판정했다" 는 근거다. 옮긴 문장을 먼저
   쓰고, **원문을 괄호 안에 그대로 덧붙인다** — 근거는 원문이 남아야 확인할 수 있다.
   예: Language ability is not required if you can communicate openly
       (원문: オープンマインドでコミュニケーションできる方であれば語学力は問いません)
7. **software 는 도구의 공식 표기로 쓴다** — "스케치업"→SketchUp, "라이노"→Rhino.
   한글·가나로 음차된 도구 이름을 그대로 두지 마라.
8. **deadline_text 는 마감 표기다. 숫자와 형식을 절대 바꾸지 마라.**
   "~09/20(일)" 은 "~09/20(日)" 처럼 요일만 옮긴다. 날짜를 다시 쓰지 마라.
   "상시채용" 처럼 날짜가 아닌 말은 용어표대로 옮긴다.
9. pay_stated 는 공고에 적힌 급여 문구다. **금액·통화·단위를 바꾸지 마라.**
   설명하는 말(대학원졸·교통비 지급 등)만 옮긴다.
10. 아래 용어표는 그대로 따른다.

{glossary}
"""


# 프롬프트·용어표를 고치면 이미 옮겨 둔 것도 다시 옮겨야 한다. 안 그러면 해시가 같아서
# "안 바뀐 것" 으로 보고 건너뛰고, 옛 번역이 화면에 그대로 남는다. 실제로 그랬다.
PROMPT_VERSION = 5


def source_hash(bundle: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps({"v": PROMPT_VERSION, "b": bundle}, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]


def _schema() -> dict:
    one = {
        "type": "object",
        "properties": {
            **{f: {"type": "string"} for f in FIELDS_TEXT},
            **{f: {"type": "array", "items": {"type": "string"}} for f in FIELDS_LIST},
        },
    }
    return {"type": "object", "properties": {lang: one for lang in LANGS}}


def bundle_of(d: dict[str, Any]) -> dict[str, Any]:
    """공고 dict 에서 화면에 나가는 것만 뽑는다. 빈 값은 넣지 않는다."""
    out: dict[str, Any] = {}
    for f in FIELDS_TEXT:
        v = d.get(f)
        if isinstance(v, str) and v.strip():
            out[f] = v
    for f in FIELDS_LIST:
        v = d.get(f)
        if isinstance(v, list) and v:
            out[f] = [x for x in v if isinstance(x, str) and x.strip()]
    return out


def kit_dict(kit) -> dict[str, Any]:
    """메일 초안 — 발송 경로는 객체를, 저장분은 dict 를 넘긴다. 한 모양으로 맞춘다."""
    if not kit:
        return {}
    if isinstance(kit, dict):
        return kit
    return {"subject": kit.subject, "body": kit.body,
            "hooks": list(kit.hooks or []), "ask_points": list(kit.ask_points or [])}


def display_source(p, a, e, fit_why, pay=None, kit=None) -> dict[str, Any]:
    """화면·메시지에 나가는 **원문** 값 한 벌. 번역은 이걸 그대로 옮긴 것이다.

    사이트(tools/export_data.py)와 텔레그램(src/render.py)이 같은 자리를 보게 하려고
    한곳에서 만든다. 예전에는 봇이 원문 필드를, 사이트가 번역본을 따로 읽어서
    같은 공고가 두 곳에서 다르게 보였다."""
    src: dict[str, Any] = {k: getattr(p, k, None) for k in FIELDS_TEXT if hasattr(p, k)}
    src.update({
        "responsibilities": p.responsibilities, "qualifications": p.qualifications,
        "preferred": p.preferred, "firm_projects": p.firm_projects,
        "blockers_desc": a.blockers_desc, "soft_desc": a.soft_desc,
        "met": a.met, "unknowns": a.unknowns,
        "gate_label": e.label("ko"), "gate_reason": e.reason,
        "gate_evidence": e.evidence, "gate_action": e.action,
        "fit_why": fit_why,
        "pay_note": ((pay or {}).get("company_avg") or {}).get("basis"),
        "pay_stated": (pay or {}).get("stated"),
        # 마감 표기 — "~09/20(일)", "상시채용" 처럼 날짜가 아닌 것이 섞여 온다.
        # 원본(p.deadline)은 D-day 계산에 쓰므로 그대로 두고 표시용만 옮긴다.
        "deadline_text": p.deadline,
        "software": list(p.software or []),
        "company": p.company,
    })
    k = kit_dict(kit)
    if k:
        src["mail_subject"] = k.get("subject")
        src["mail_body"] = k.get("body")
        src["mail_hooks"] = k.get("hooks") or []
        src["mail_asks"] = k.get("ask_points") or []
    return src


HANGUL = re.compile(r"[가-힣]")
# 가운뎃점(・U+30FB)은 중국어 표기에도 쓴다 — 잔존으로 보면 오탐이다
KANA = re.compile(r"[\u3040-\u309F\u30A0-\u30FA\u30FC-\u30FF]")   # ひらがな·カタカナ
# 회사명·작품명은 원문을 그대로 두는 게 맞다. 검사에서 뺀다.
# gate_evidence 는 번역 뒤에 원문을 일부러 병기한다 — 잔존이 아니다
KEEP_ORIGINAL = {"company", "firm_projects", "gate_evidence"}


def _hangul_left(data: dict[str, Any]) -> list[str]:
    """en·zh_TW 결과에 한국어·일본어가 그대로 남은 필드 이름들."""
    out = []
    for lang in ("en", "zh_TW"):
        for k, v in (data.get(lang) or {}).items():
            if k in KEEP_ORIGINAL:
                continue
            txt = " ".join(v) if isinstance(v, list) else str(v or "")
            if HANGUL.search(txt) or KANA.search(txt):
                out.append(f"{lang}.{k}")
    return out


def _repair(client, data: dict[str, Any], leftovers: list[str], cfg: dict, model_name: str) -> None:
    """옮기다 만 조각만 짚어서 다시 옮긴다. 실패하면 그냥 둔다 (원문이라도 보이는 게 낫다)."""
    from google.genai import types

    LANG_NAME = {"en": "영어", "zh_TW": "번체중문"}
    for ref in leftovers:
        lang, _, field = ref.partition(".")
        cur = (data.get(lang) or {}).get(field)
        if cur in (None, "", []):
            continue
        payload = json.dumps({"text": cur}, ensure_ascii=False)
        try:
            r = client.models.generate_content(
                model=model_name,
                contents=(f"아래 값을 {LANG_NAME.get(lang, lang)} 로 옮겨라. 원문 언어가 한 글자도 남으면 안 된다.\n"
                          f"회사명·프로젝트명만 원문을 남긴다. 리스트면 길이를 그대로 둔다.\n\n{payload}"),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={"type": "object", "properties": {
                        "text": ({"type": "array", "items": {"type": "string"}}
                                 if isinstance(cur, list) else {"type": "string"})}},
                    temperature=0.1,
                ),
            )
            got = (json.loads(r.text) or {}).get("text") if r.text else None
            if got and (not isinstance(cur, list) or len(got) == len(cur)):
                data[lang][field] = got
        except Exception:
            continue


def translate(client, bundle: dict[str, Any], cfg: dict,
              focus: Optional[list[str]] = None, attempt_left: int = 2
              ) -> Optional[dict[str, Any]]:
    """{ko: {...}, en: {...}, zh_TW: {...}}. 실패하면 None."""
    if not bundle:
        return None
    from google.genai import types

    from .extract import _models

    last: Exception | None = None
    prompt = ("아래 JSON 을 세 언어로 옮겨라. 키 이름과 리스트 길이는 그대로 두고 값만 옮긴다.\n\n"
              + json.dumps(bundle, ensure_ascii=False, indent=1))
    if focus:
        prompt += ("\n\n★ 지난번에 이 자리들에 한국어가 그대로 남았다. 이번엔 반드시 그 언어로 옮겨라:\n"
                   + "\n".join(f"  - {f}" for f in focus))
    for model_name in _models(cfg):
        try:
            r = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM.format(glossary=GLOSSARY),
                    response_mime_type="application/json",
                    response_schema=_schema(),
                    temperature=0.2,
                ),
            )
            data = json.loads(r.text) if r.text else None
            if not data:
                continue
            # 영어·번체중문 결과에 한글이 남아 있으면 옮기다 만 것이다. 한 번 더 부른다.
            leftovers = _hangul_left(data)
            # 남은 게 한두 조각이면 그것만 따로 옮긴다. 통째로 다시 부르는 것보다 잘 된다.
            if leftovers and attempt_left <= 0:
                _repair(client, data, leftovers, cfg, model_name)
                leftovers = _hangul_left(data)
            if leftovers and attempt_left > 0:
                again = translate(client, bundle, cfg, focus=leftovers,
                                  attempt_left=attempt_left - 1)
                # 나아졌을 때만 갈아탄다. 더 나빠진 걸 받으면 안 된다.
                if again and len(_hangul_left(again)) < len(leftovers):
                    return again
            # 리스트 길이가 어긋나면 원문을 잃은 것이다 — 그건 쓰지 않는다
            for lang in LANGS:
                got = data.get(lang) or {}
                for f in FIELDS_LIST:
                    if f in bundle and len(got.get(f) or []) != len(bundle[f]):
                        got[f] = bundle[f]
            return {lang: data.get(lang) or {} for lang in LANGS}
        except Exception as e:
            last = e
            continue
    import sys
    print(f"    번역 실패: {type(last).__name__}: {str(last)[:120]}", file=sys.stderr)
    return None
