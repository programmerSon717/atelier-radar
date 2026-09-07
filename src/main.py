"""오케스트레이터.

  python -m src.main            # 평소 실행 (Tier1 → 바뀐 곳만 Tier2)
  python -m src.main --sweep    # 전체 훑기 (주 1회)
  python -m src.main --only kr-101,jp-kkaa-tokyo
  python -m src.main --dry-run  # 텔레그램 안 보내고 표준출력으로만
"""
import argparse
import asyncio
import os
import sys
from datetime import date

from dotenv import load_dotenv

from . import notify, outreach, store
from . import eligibility, relevance, salary, verified
from .match import assess, is_new_grad_ok
from .scope import country_of, in_scope
from .render import load_locale, render_posting, render_summary
from .extract import extract_many
from .targets import Office, load_config, load_offices
from .watch import now_iso, watch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 채용페이지를 이만큼 연속으로 못 긁으면 해시 감시가 무의미하다 → LLM 에게 맡긴다
FAIL_ESCALATE_AT = 3


async def pick_targets(
    offices: list[Office], cfg: dict, sweep: bool
) -> tuple[list[tuple[Office, str, str]], list[str]]:
    """Tier1 을 돌려서 Tier2 로 넘길 (office, url, 페이지텍스트) 를 고른다.

    검색 그라운딩을 안 쓰므로 페이지 본문을 여기서 확보해야 한다.
    sweep 이면 해시를 무시하고 가져와진 것 전부를 넘긴다."""
    conn = store.connect()
    now = now_iso()
    results = await watch(offices, cfg["watch"]["timeout_seconds"], cfg["watch"]["max_parallel"])

    picked: list[tuple[Office, str, str]] = []
    errors: list[str] = []
    for office, text, err in results:
        url = office.careers_url or ""
        if err:
            n = store.record_fetch_failure(conn, office.id, url, now)
            # 매번 시끄럽게 알리지 않고, 임계치에 닿을 때만 사람에게 알린다
            if n == FAIL_ESCALATE_AT or sweep:
                errors.append(f"{office.id}: {err} → 수동 확인 필요")
            continue
        if store.page_changed(conn, office.id, text) or sweep:
            picked.append((office, url, text))
    conn.close()
    return picked, errors


async def run(sweep: bool, only: list[str] | None, dry_run: bool) -> int:
    cfg = load_config()
    L = load_locale(cfg.get("locale", "ko"))
    offices = load_offices()
    by_id = {o.id: o for o in offices}

    if only:
        offices = [by_id[i] for i in only if i in by_id]
        missing = [i for i in only if i not in by_id]
        if missing:
            print(f"알 수 없는 office id: {', '.join(missing)}", file=sys.stderr)
        if not offices:
            return 1

    pages, errors = await pick_targets(offices, cfg, sweep or bool(only))
    print(f"[tier1] {len(offices)}개 확인 → {len(pages)}개 추출 대상", file=sys.stderr)

    reports = await extract_many(pages, cfg)
    page_text = {o.id: (u, t) for o, u, t in pages}

    gclient = None
    if cfg.get("outreach", {}).get("enabled", True):
        try:
            from .extract import _client
            gclient = _client()
        except Exception as e:
            errors.append(f"메일 초안 생성 비활성: {e}")

    conn = store.connect()
    now = now_iso()
    sent = 0
    for office_id, report, err in reports:
        if err:
            # 추출이 실패했으면 해시를 저장하지 않는다 → 다음 실행이 다시 시도한다
            errors.append(f"{office_id}: {err}")
            continue
        if report is None:
            continue
        office = by_id[office_id]
        office_ok = True
        for p in report.postings:
            # 추적 범위는 한국·일본·대만뿐. 같은 사무소라도 뉴욕·파리 자리는 버린다.
            ok, why = in_scope(p, office.country)
            if not ok:
                print(f"[scope] {office_id}: {p.title} — {why}", file=sys.stderr)
                continue
            key = store.posting_key(p.office_id, p.title, p.source_url)
            if store.already_sent(conn, key):
                # 다시 보내지는 않지만, 이번에 더 정확히 읽었으면 저장분을 고친다.
                # (사이트는 저장분으로 그려진다 — 안 고치면 첫 판독에 영원히 묶인다)
                if not dry_run and store.refresh_payload(conn, key, p):
                    print(f"[갱신] {office_id}: {p.title}", file=sys.stderr)
                continue
            # 사람이 원문을 직접 확인한 것이 있으면 모델 추출보다 먼저다
            verified.apply(p)
            pc = country_of(p, office.country)   # 글로벌 페이지는 공고마다 나라가 다르다
            a = assess(p, pc, office)
            # 경력 0년이라 경력직 공고는 지원 자체가 안 된다 — 라벨이 아니라 제외한다
            if cfg.get("filter", {}).get("new_grad_only", True) and not is_new_grad_ok(a, p.track):
                print(f"[skip] {office_id}: {p.title} — 경력직 요건", file=sys.stderr)
                continue
            # 학력을 안 보는 자리는 건축 석사가 갈 자리가 아니다 — 라벨이 아니라 제외한다
            nd = relevance.drop_for_no_degree(p, office)
            if nd and cfg.get("filter", {}).get("drop_no_degree", True):
                print(f"[skip] {office_id}: {p.title} — 학력무관 ({nd})", file=sys.stderr)
                continue
            # 갈 만한 곳인지부터 본다. 이름 모를 사무소 공고가 쏟아지면 정작 봐야 할
            # 공고가 묻힌다 (사용자 지시: 101·켄고쿠마 급을 가져와라)
            if relevance.career_only(p):
                print(f"[skip] {office_id}: {p.title} — 제목이 경력직 전용", file=sys.stderr)
                continue
            st = relevance.special_track(p)
            if st:
                print(f"[skip] {office_id}: {p.title} — 특정 대상 전형({st})", file=sys.stderr)
                continue
            ok_firm, why_firm = relevance.worth_applying(p, office)
            if not ok_firm and cfg.get("filter", {}).get("known_firms_only", True):
                print(f"[skip] {office_id}: {p.title} — {why_firm}", file=sys.stderr)
                continue
            # 설계 역량을 쌓을 수 없는 곳은 보내지 않는다 (근거 있는 경우만 제외)
            # 설계직이 아니거나 시공사면 보내지 않는다 (라벨만 붙여 보내면 목록이 흐려진다)
            if relevance.is_low_fit(relevance.label(p, office)) \
                    and cfg.get("filter", {}).get("drop_low_fit", True):
                print(f"[skip] {office_id}: {p.title} — 설계직 아님/시공사", file=sys.stderr)
                continue
            grade, why = relevance.firm_grade(p, office)
            if grade == "weak" and cfg.get("filter", {}).get("drop_weak_firms", True):
                print(f"[skip] {office_id}: {p.title} — {why}", file=sys.stderr)
                continue

            elig = eligibility.judge(p, pc)
            pay = salary.describe(p, pc, office.tier)

            # 문의가 필요한 건에만 메일 초안을 만든다 (호출 아끼기)
            kit = None
            if gclient and elig.gate in ("ask", "domestic"):
                kit = await asyncio.to_thread(
                    outreach.draft, gclient, p, p.company or office.display_name,
                    pc, a.unknowns, cfg)

            fit = relevance.fit_grade(p, office, a)
            text = render_posting(p, office, a, L, elig, kit, pay, fit)
            if dry_run:
                print("\n" + "─" * 60 + "\n" + text)
            else:
                delivered, failed = await notify.send_ok(text, country=pc)
                if failed:
                    errors.extend(failed)
                    office_ok = False
                if not delivered:
                    continue  # 아무 데도 못 갔을 때만 미발송으로 남긴다
            store.mark_sent(conn, key, p, now, kit)
            sent += 1
        # 추출과 발송이 다 끝난 뒤에야 "이 페이지는 봤다" 고 기록한다
        if office_ok and not dry_run and office_id in page_text:
            u_, t_ = page_text[office_id]
            store.commit_page_hash(conn, office_id, u_, t_, now)

        for u in report.unresolved:
            print(f"[unresolved] {office_id}: {u}", file=sys.stderr)

    if sweep:
        store.log_sweep(conn, now)
    conn.close()

    summary = render_summary(len(offices), sent, errors, L)
    if dry_run:
        print("\n" + "=" * 60 + "\n" + summary)
    elif sent or errors:
        await notify.send(summary)
    from .clock import today_in
    print(f"[done] 로컬 {date.today()} / 한국 {today_in('KR')} — "
          f"신규 {sent}건, 오류 {len(errors)}건", file=sys.stderr)
    return 0


def main() -> int:
    load_dotenv(os.path.join(ROOT, ".env"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="Tier1 건너뛰고 전체 리서치")
    ap.add_argument("--only", help="office id 쉼표 구분")
    ap.add_argument("--dry-run", action="store_true", help="텔레그램 발송 없이 출력만")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    return asyncio.run(run(args.sweep, only, args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
