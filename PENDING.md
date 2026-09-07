# 대기 중인 것 (세션 끊겨도 여기 보고 이어가기)

최종 갱신: 2026-09-07

## 사용자가 줘야 진행되는 것
- [ ] **GitHub Actions 시크릿 등록 확인** — 리포 Settings → Secrets 에 7개가 있어야 한다.
      `GEMINI_API_KEY` `TELEGRAM_BOT_TOKEN` `TELEGRAM_CHAT_IDS`
      `TELEGRAM_TOPIC_KR/JP/TW` `CANDIDATE_NAME` (+ 새로 추가된 `CANDIDATE_SCHOOL`)
      없으면 클라우드에서 아예 안 돈다. 마지막 실행 기록은 전부 로컬 실행이다.
- [ ] 여자친구분도 알림 받을지 (받으면 그분도 봇에 /start 필요)

## 다음에 할 것
1. **careers_url 계속 채우기** — 53곳 중 30곳 확보. 남은 23곳은 아래 "URL 미해결"
2. zh_TW 전환 — locale 한 줄 + zh_TW.yaml 을 네이티브급으로 다듬기 (현재 초벌 번역)
3. 대만 공고가 아직 적다. 자사 사이트가 대부분 SPA

## 끝난 것 (2026-09-07)
- 텔레그램 chat id·토픽 등록, GitHub Actions 워크플로(10분 watch + 주간 sweep) — 9/6 밤
- 한자 숫자 경력 요건 탐지 (三年以上). 경력직 2건이 신입으로 새어나가고 있었다
- 학력무관 공고 제외 (`drop_no_degree`)
- 추천/중립/비추천 3단계 등급 — 포트폴리오 접점 기준. 텔레그램·웹 둘 다
- 문의 메일 재작성 — 법인격 표기 제거, AI 메타 서술 금지, 뉴스로 근거 확보
- `tools/test_gates.py` 회귀 검사. **게이트를 건드렸으면 반드시 돌린다**

## 결정된 것
- **LLM: Gemini** (사용자 키). 무료 티어. 모델: gemini-3.5-flash 계열 폴백 체인.
  검색 그라운딩은 429(할당량 없음) → 안 쓴다. httpx 로 페이지를 직접 긁어 넘긴다.
- 사무소 프로젝트를 페이지에서 못 읽으면 **Google 뉴스 RSS** 로 근거를 찾는다 (`src/news.py`)
- 일본 타겟 B안: 전부 추적하되 언어요건 라벨만 붙인다
- 켄고쿠마는 인턴→정규직 공식 경로 없음 (`data/verified/kkaa.yaml`)

## 알려진 한계
- **JS 렌더링 페이지는 못 긁는다.** 특히 한국의 `*.recruiter.co.kr` ATS 는 전부 0자.
  → 잡코리아 회사페이지로 우회 (희림에서 검증됨). 사람인도 같은 방식 가능.
- tw-jjp(潘冀) 는 자사 채용 URL 미발견, 104 는 403 차단 (우회하지 않기로 함)

## URL 미해결 (23곳)
JP: mjd, takenaka, sanaa, nishizawa, toyoito, ando, oh, soufujimoto, kkaa-seoul 외
KR: samoo, haeahn, kunwon, dagroup, 101, massstudies, iarc, wondoshi, unsangdong,
    kkaa-seoul, gensler-seoul, aedas-seoul, sigongtech
TW: jjp, artech(SPA), daju, formosstudio, helei, cosine, zhujian, jingxiang
