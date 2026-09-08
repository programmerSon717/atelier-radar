// data.json 을 읽어 화면을 그린다. HTML 에 데이터를 굽지 않으므로
// 봇이 새 데이터를 올리면 페이지를 다시 만들지 않아도 갱신된다.
const E = (s) => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]))
  // 이름·학교는 공개 사이트에 싣지 않는다. 자리만 남기고 화면 언어로 채운다.
  .replace(/\[NAME\]/g, () => T("name_ph")).replace(/\[SCHOOL\]/g, () => T("school_ph"));

// ── 언어 ─────────────────────────────────────────────
// 화면 문구는 ui.js 의 UI, 공고 내용은 data.json 의 i18n 에서 온다.
let LANG = (localStorage.getItem("lang") || "").trim();
if (!UI[LANG]) LANG = "ko";

function T(key, vars) {
  let v = (UI[LANG] && UI[LANG][key]) ?? (UI.ko[key] ?? key);
  if (vars) for (const [k, x] of Object.entries(vars)) v = v.replaceAll("{" + k + "}", x);
  return v;
}

// 공고 한 건에서 지금 언어의 값을 꺼낸다. 번역이 아직 없으면 원문을 그대로 쓴다.
function F(p, field) {
  const t = p && p.i18n && p.i18n[LANG];
  const v = t && t[field];
  if (Array.isArray(v) ? v.length : (v !== undefined && v !== null && v !== "")) return v;
  return p ? p[field] : undefined;
}

const GATES = [
  { k: "open",     v: "--open" },
  { k: "ask",      v: "--ask" },
  { k: "native",   v: "--native" },
  { k: "domestic", v: "--domestic" },
  { k: "closed",   v: "--closed" },
].map(g => ({ ...g, get t() { return T("g_" + g.k); }, get d() { return T("g_" + g.k + "_d"); } }));
const FLAG = { KR: "🇰🇷", JP: "🇯🇵", TW: "🇹🇼" };
const TRACK_KEY = { new_grad: "track_new_grad", intern: "track_intern",
                    intern_to_fulltime: "track_intern_ft", entry_level: "track_new_grad",
                    year_round: "track_year_round", other: "tier_other" };
const trackLabel = (k) => T(TRACK_KEY[k] || "tier_other");

let DATA = null;
const state = { country: "all", gates: new Set(), q: "", view: "live" };

// 마감은 반드시 **공고가 있는 나라 시각**으로 센다.
// 브라우저는 보는 사람의 시간대(미국 동부 등)를 쓰는데, 한국과 13~14시간 차이가 나서
// 그대로 계산하면 이미 끝난 공고가 "오늘 마감"으로 보인다. 실제로 그렇게 틀렸다.
const TZ_OFFSET = { KR: 9, JP: 9, TW: 8 };   // 셋 다 서머타임 없음

function todayIn(country) {
  const off = TZ_OFFSET[country] ?? 9;
  const t = new Date(Date.now() + off * 3600000);
  return t.toISOString().slice(0, 10);       // 그 나라의 '오늘'
}

function daysLeft(d, country) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d || "")) return null;
  const today = todayIn(country);
  return Math.round((Date.parse(d + "T00:00:00Z") - Date.parse(today + "T00:00:00Z")) / 86400000);
}

function render() {
  paintOpenApply();      // 나라 필터가 바뀌면 이 목록도 같이 따라간다
  const P = DATA.postings;
  const gc = Object.fromEntries(GATES.map(g => [g.k, P.filter(p => p.gate === g.k).length]));

  document.getElementById("gates").innerHTML = GATES.map(g => `
    <button class="gate" style="--g:var(${g.v})" data-g="${g.k}"
            aria-pressed="${state.gates.has(g.k)}">
      <span class="n">${gc[g.k] || 0}</span>
      <span class="t">${g.t}</span>
      <span class="d">${E(g.d)}</span>
    </button>`).join("");

  // 상황별 안내 — 지금 데이터에서 실제로 셀 수 있는 것만 말한다
  const soon = P.filter(p => { const d = daysLeft(p.deadline, p.country); return d !== null && d >= 0 && d <= 14; });
  const openTw = P.filter(p => p.gate === "open" && p.country === "TW").length;
  const openOther = P.filter(p => p.gate === "open" && p.country !== "TW").length;
  const intern = P.filter(p => /intern/.test(p.track) && p.gate !== "closed").length;
  const guide = [
    [T("q_now"),
     `<b>${T("g_open")} ${gc.open || 0}</b> — ${T("tw")} ${openTw} · ${T("q_now_other")} ${openOther}`],
    [T("q_soon"),
     soon.length ? `<b>${T("q_soon_n", { n: soon.length })}</b> — ${soon.slice(0,3).map(s=>{
       const d=daysLeft(s.deadline, s.country);
       return `${E(F(s, "company")||s.office_name)} <b>${d===0?T("today_due"):"D-"+d}</b>`;}).join(" · ")}` : T("none_soon")],
    [T("q_intern"), `<b>${T("q_intern_n", { n: intern })}</b>`],
    [T("q_korean"), T("a_korean", { n: gc.ask || 0 })],
    [T("q_domestic"), T("a_domestic", { n: gc.domestic || 0 })],
  ];
  document.getElementById("guide").innerHTML =
    guide.map(([q, a]) => `<tr><td>${E(q)}</td><td>${a}</td></tr>`).join("");

  // 필터
  const q = state.q.trim().toLowerCase();
  let list = P.filter(p =>
    (state.country === "all" || p.country === state.country) &&
    (state.gates.size === 0 || state.gates.has(p.gate)) &&
    (state.view === "past" ? p.expired : !p.expired) &&
    (!q || [p.title, p.company, p.office_name, p.location, (p.software || []).join(" ")]
        .join(" ").toLowerCase().includes(q)));

  const rank = { open: 0, ask: 1, native: 2, domestic: 3, closed: 4 };
  if (state.view === "past") {
    // 지난 공고는 최근 마감순 — 작년 이맘때 뭐가 떴는지 보려는 거다
    list.sort((a, b) => String(b.deadline || "").localeCompare(String(a.deadline || "")));
  } else {
    // 마감이 임박한 건 게이트보다 먼저다. 오늘 마감을 아래에 두면 놓친다
    const urg = (p) => { const d = daysLeft(p.deadline, p.country); return d !== null && d <= 3 ? 0 : 1; };
    list.sort((a, b) => (urg(a) - urg(b))
      || (rank[a.gate] - rank[b.gate])
      || ((daysLeft(a.deadline, a.country) ?? 9e3) - (daysLeft(b.deadline, b.country) ?? 9e3)));
  }

  const inC = (p) => state.country === "all" || p.country === state.country;
  const live = P.filter(p => inC(p) && !p.expired).length;
  const past = P.filter(p => inC(p) && p.expired).length;
  document.querySelector('.chip[data-v="live"]').textContent = `${T("live")} ${live}`;
  document.querySelector('.chip[data-v="past"]').textContent = `${T("past")} ${past}`;
  document.getElementById("count").textContent = `${T("count", { n: list.length })}`;
  syncClearButton();
  // 지난 공고 탭에서는 아카이브(가벼운 과거 기록)도 같이 보여준다
  if (state.view === "past") {
    const q2 = state.q.trim().toLowerCase();
    const arch = (DATA.archive || []).filter(a =>
      (state.country === "all" || a.country === state.country) &&
      (!q2 || `${a.company} ${a.title}`.toLowerCase().includes(q2)));
    list = list.concat(arch.map(a => ({
      ...a, archive: true, gate: "ask", gate_icon: "🗄",
      gate_label: T("archive_h"), gate_reason: T("archive_note"),
      track: "other", expired: true, deadline: a.deadline || a.posted_at,
      source_url: a.url, office_name: a.company, summary: "",
    })));
    list.sort((a, b) => String(b.deadline || b.posted_at || "")
      .localeCompare(String(a.deadline || a.posted_at || "")));
    document.getElementById("count").textContent = T("count", { n: list.length });
  syncClearButton();
  }

  const rowsEl = document.getElementById("rows");
  if (!list.length) {
    rowsEl.innerHTML = `<p class="empty">${state.view === "past"
      ? T("empty_past") : T("empty")}</p>`;
    return;
  }
  if (state.view === "past" && state.country === "all") {
    // 지난 공고는 나라별로 묶어서 본다 — 어느 나라가 언제 뽑았는지가 요점이다
    const order = ["KR", "JP", "TW"];
    const NAME = { KR: T("kr"), JP: T("jp"), TW: T("tw") };
    rowsEl.innerHTML = order.filter(c => list.some(p => p.country === c)).map(c => {
      const g = list.filter(p => p.country === c);
      const years = [...new Set(g.map(p => (p.deadline || "").slice(0, 4)).filter(Boolean))];
      return `<div class="grouphead">${NAME[c]} <span>${T("count", { n: g.length })}${
        years.length ? " · " + years.sort().reverse().join(" / ") : ""}</span></div>`
        + g.map(row).join("");
    }).join("");
  } else {
    rowsEl.innerHTML = list.map(row).join("");
  }
}

function bullets(items, label) {
  if (!items || !items.length) return "";
  return `<div><h4>${label}</h4><ul>${items.map(x => `<li>${E(x)}</li>`).join("")}</ul></div>`;
}

// 메일은 두 벌을 보여준다.
//  · 읽는 사람 말로 옮긴 것 — 무슨 내용인지 알아야 하니까
//  · 보낼 원문 — 한국 사무소에 영어로 보낼 수는 없다. 복사 버튼은 이쪽을 집는다.
function mailBlock(k, p) {
  const id = "m" + Math.random().toString(36).slice(2, 9);
  const subj = F(p, "mail_subject") || k.subject;
  const body = F(p, "mail_body") || k.body;
  const hooks = F(p, "mail_hooks") || k.hooks || [];
  const asks = F(p, "mail_asks") || k.ask_points || [];
  const translated = body !== k.body;
  return `<details class="mail" open><summary>📨 ${T("mail_h")}</summary>
    <div class="jd" style="grid-template-columns:1fr">
      <div><h4>${T("mail_subject")}</h4><p>${E(subj)}</p></div>
      <div><h4>${T("mail_body")}</h4><p style="white-space:pre-wrap">${E(body)}</p></div>
      ${translated ? `<div><h4>${T("mail_original")}</h4>
        <p class="note" style="margin:0 0 6px">${T("mail_send_note")}</p>
        <p id="${id}" style="white-space:pre-wrap;opacity:.85">${E(k.body)}</p>
        <button class="chip" style="margin-top:9px" data-copy="${id}">${T("mail_copy")}</button></div>`
      : `<div><p id="${id}" hidden>${E(k.body)}</p>
        <button class="chip" data-copy="${id}">${T("mail_copy")}</button></div>`}
      ${hooks.length ? `<div><h4>${T("hooks")}</h4><ul>${hooks.map(x=>`<li>${E(x)}</li>`).join("")}</ul></div>` : ""}
      ${asks.length ? `<div><h4>${T("asks")}</h4><ul>${asks.map(x=>`<li>${E(x)}</li>`).join("")}</ul></div>` : ""}
    </div></details>`;
}

function row(p) {
  if (p.archive) {
    const when = p.posted_at ? `${T("posted")} ${E(p.posted_at)}` : "";
    const dl = p.deadline && p.deadline !== p.posted_at ? ` · ${T("deadline")} ${E(p.deadline)}` : "";
    return `<article class="row arch" style="--g:var(--closed)">
      <div class="stripe"></div><div class="rbody">
        <div class="rtop"><span class="gatechip">🗄 ${T("archive_h")}</span>
          <span class="rtitle">${E(F(p, "title"))}</span>
          <span class="rfirm">${E(p.company || "")}</span></div>
        <div class="meta"><span>${when}${dl}</span><span>·</span><span>vmspace</span></div>
        <p style="margin:9px 0 0"><a class="src" href="${E(p.url)}" target="_blank" rel="noopener">${T("source")}</a></p>
      </div></article>`;
  }
  const g = GATES.find(x => x.k === p.gate) || GATES[1];
  const dl = daysLeft(p.deadline, p.country);
  const meta = [
    FLAG[p.country] + " " + E(F(p, "location") || p.office_name),
    trackLabel(p.track),
    // 고용형태가 트랙과 같은 말이면 두 번 쓰지 않는다 ("인턴 · 인턴")
    p.employment_type && !new RegExp(trackLabel(p.track) || "\u0000").test(F(p, "employment_type"))
      && !/^(intern(ship)?|인턴)$/i.test(p.employment_type.trim()) ? E(F(p, "employment_type")) : "",
    p.deadline ? `<span class="${dl !== null && dl <= 14 ? "due" : ""}">${p.expired ? T("expired") : T("deadline")} ${E(p.deadline)}${dl !== null && dl >= 0 && dl <= 30 ? ` (D-${dl})` : ""}</span>` : "",
  ].filter(Boolean);

  const facts = [[T("cond_employ"), F(p, "employment_type")],
                 [T("cond_process"), F(p, "process")], [T("cond_lang"), F(p, "language_required")]]
    .filter(([, v]) => v).map(([k, v]) => `${E(k)}: ${E(v)}`);

  const jd = [
    bullets(F(p, "responsibilities"), T("resp")),
    bullets(F(p, "qualifications"), T("qual")),
    bullets(F(p, "preferred"), T("pref")),
    p.software?.length ? `<div><h4>${T("soft")}</h4><p>${E(p.software.join(" · "))}</p></div>` : "",
    facts.length ? `<div><h4>${T("cond")}</h4><p>${facts.join("<br>")}</p></div>` : "",
    F(p, "notes") ? `<div><h4>${T("unknown_h")}</h4><p>${E(F(p, "notes"))}</p></div>` : "",
    (p.contact_email || p.contact_phone || p.apply_how)
      ? `<div><h4>${T("contact_h")}</h4><p>${[
          p.contact_email ? `✉️ <a class="src" href="mailto:${E(p.contact_email)}">${E(p.contact_email)}</a>` : "",
          p.contact_phone ? `☎️ ${E(p.contact_phone)}` : "",
          F(p, "apply_how") ? E(F(p, "apply_how")) : ""].filter(Boolean).join("<br>")}</p></div>` : "",
    bullets(F(p, "firm_projects"), T("projects")),
    p.pay ? `<div><h4>${T("pay")}</h4><p>${[
        p.pay.stated ? `${T("pay_stated")}: <b>${E(p.pay.stated)}</b>`
                     : (p.salary ? `${T("pay_stated")}: ${E(p.salary)} <span style="opacity:.6">${T("pay_noamt")}</span>` : ""),
        p.pay.company_avg ? `<span class="rumor">${T("pay_ref")}</span> ${T("pay_avg")} <b>${E(payValue(p.pay.company_avg.average, p.country))}</b>` : "",
        p.pay.company_avg ? `<span style="opacity:.6">${E(F(p, "pay_note") || p.pay.company_avg.basis)} · ${T("pay_src")}: ${E(sourceName(p.pay.company_avg.source))}</span>` : "",
        (!p.pay.stated && !p.salary && !p.pay.company_avg) ? `<span style="opacity:.6">${T("pay_none")}</span>` : "",
      ].filter(Boolean).join("<br>")}</p></div>` : "",
    bullets(F(p, "blockers_desc"), T("blockers")),
    bullets(F(p, "soft_desc"), T("softb")),
    bullets(F(p, "met"), T("met")),
    bullets(F(p, "unknowns"), T("unknowns")),
  ].join("");

  return `<article class="row" style="--g:var(${g.v})">
    <div class="stripe"></div>
    <div class="rbody">
      <div class="rtop">
        <span class="gatechip">${p.gate_icon} ${E(F(p, "gate_label") || g.t)}</span>
        ${fitChip(p)}
        <span class="rtitle">${E(F(p, "title"))}</span>
        <span class="rfirm">${E(F(p, "company") || p.office_name)}</span>
      </div>
      ${dl !== null && dl >= 0 && dl <= 3 ? `<p class="urgent">🚨 ${dl === 0 ? T("today_due") : T("due_in", { n: dl })}</p>` : ""}
      <div class="meta">${meta.map(m => `<span>${m}</span>`).join("<span>·</span>")}</div>
      <p class="why"><b>${E(F(p, "gate_label"))}</b> — ${E(F(p, "gate_evidence") || F(p, "gate_reason"))}</p>
      ${F(p, "gate_action") ? `<p class="act">👉 ${E(F(p, "gate_action"))}</p>` : ""}
      ${F(p, "summary") ? `<p class="why">${E(F(p, "summary"))}</p>` : ""}
      ${jd ? `<div class="jd">${jd}</div>` : `<p class="thin">${T("thin")}</p>`}
      ${p.outreach ? mailBlock(p.outreach, p) : ""}
      <p style="margin:10px 0 0"><a class="src" href="${E(p.source_url)}" target="_blank" rel="noopener">${T("source")}</a></p>
    </div></article>`;
}

// 지원 추천도 — 사무소 수준과 포트폴리오 접점으로 매긴다 (src/relevance.py: fit_grade)
const FIT = {
  recommend: { k: "fit_recommend", i: "\u{1F44D}", c: "#2f7d51" },
  neutral:   { k: "fit_neutral",   i: "\u2796",    c: "#8a8a8a" },
  avoid:     { k: "fit_avoid",     i: "\u{1F44E}", c: "#a3452f" },
};

// 연봉은 나라마다 단위가 다르다. "8,460만원" 을 영어 화면에 그대로 두면 읽을 수 없다.
function payValue(v, country) {
  const raw = String(v ?? "");
  if (LANG === "ko") return raw;
  let m = /^([\d,]+)\s*만원$/.exec(raw);
  if (m) {
    const won = parseInt(m[1].replace(/,/g, ""), 10) * 10000;
    return LANG === "en" ? "KRW " + won.toLocaleString("en-US") : m[1] + "萬韓元";
  }
  m = /^([\d,]+)\s*万円$/.exec(raw);
  if (m) return LANG === "en" ? "JPY " + (parseInt(m[1].replace(/,/g, ""), 10) * 10000).toLocaleString("en-US")
                              : m[1] + "萬日圓";
  return raw;
}

// 출처 이름도 그 언어 표기로
const SOURCE_KEY = { "사람인 기업정보": "src_saramin" };
function sourceName(v) {
  const k = SOURCE_KEY[v];
  return k ? T(k) : v;
}

function fitChip(p) {
  const f = FIT[p.fit];
  if (!f) return "";
  const why = (F(p, "fit_why") || []).join(" · ");
  return `<span class="fitchip" style="--fc:${f.c}" title="${E(why)}">${f.i} ${T(f.k)}</span>`;
}

function syncClearButton() {
  const on = state.country !== "all" || state.gates.size > 0 || state.q.trim() !== "";
  const el = document.getElementById("clear");
  if (el) el.hidden = !on;
}

function bind() {
  document.querySelectorAll(".lang").forEach(b =>
    b.addEventListener("click", () => setLang(b.dataset.lang)));

  document.getElementById("clear").addEventListener("click", () => {
    state.country = "all"; state.gates.clear(); state.q = "";
    document.getElementById("q").value = "";
    document.querySelectorAll(".chip[data-c]").forEach(x =>
      x.setAttribute("aria-pressed", String(x.dataset.c === "all")));
    render();
  });
  document.getElementById("gates").addEventListener("click", e => {
    const b = e.target.closest(".gate"); if (!b) return;
    const k = b.dataset.g;
    state.gates.has(k) ? state.gates.delete(k) : state.gates.add(k);
    render();
  });
  document.querySelectorAll(".chip[data-c]").forEach(b => b.addEventListener("click", () => {
    // 켠 걸 다시 누르면 꺼진다 — 켜기만 되고 못 끄면 손이 막힌다
    state.country = (state.country === b.dataset.c) ? "all" : b.dataset.c;
    document.querySelectorAll(".chip[data-c]").forEach(x =>
      x.setAttribute("aria-pressed", String(x.dataset.c === state.country)));
    render();
  }));
  document.querySelectorAll(".chip[data-v]").forEach(b => b.addEventListener("click", () => {
    if (state.view === b.dataset.v) return;   // 진행중/지난은 둘 중 하나는 켜져 있어야 한다
    state.view = b.dataset.v;
    document.querySelectorAll(".chip[data-v]").forEach(x =>
      x.setAttribute("aria-pressed", String(x === b)));
    render();
  }));
  document.getElementById("rows").addEventListener("click", async e => {
    const b = e.target.closest("[data-copy]"); if (!b) return;
    const t = document.getElementById(b.dataset.copy)?.innerText || "";
    try { await navigator.clipboard.writeText(t); b.textContent = T("mail_copied"); }
    catch { b.textContent = T("mail_failed"); }
    setTimeout(() => (b.textContent = T("mail_copy")), 2200);
  });
  document.getElementById("q").addEventListener("input", e => {
    state.q = e.target.value; render();
  });
}

// 봇은 하루에도 여러 번 새 데이터를 올린다. 화면을 열어 둔 채로도 그걸 받아야 한다.
// 브라우저 캐시를 타지 않게 no-store 로 받고, 생성 시각이 바뀌었을 때만 다시 그린다.
const POLL_MS = 60_000;

async function fetchData() {
  const r = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

const tierLabel = (t) => T({ atelier: "tier_atelier", large: "tier_large", mid: "tier_mid", global: "tier_global" }[t] || "tier_other");

// 공고를 내지 않는 사무소. 한국 아틀리에는 대부분 여기 속한다 —
// 공고를 기다리는 게 아니라 포트폴리오를 보내는 자리다.
function paintOpenApply() {
  const box = document.getElementById("openlist");
  if (!box) return;
  const list = (DATA.open_apply || []).filter(o =>
    state.country === "all" || o.country === state.country);
  document.getElementById("open-sec").hidden = list.length === 0;
  document.getElementById("open-h").textContent =
    T("open_h", { n: list.length });
  box.innerHTML = list.map(o => {
    const links = [];
    if (o.email) links.push(`<a class="mail" href="mailto:${E(o.email)}">${E(o.email)}</a>`);
    if (o.site) links.push(`<a href="${E(o.site)}" target="_blank" rel="noopener">${T("site_link")}</a>`);
    if (o.careers_url) links.push(`<a href="${E(o.careers_url)}" target="_blank" rel="noopener">${T("careers_link")}</a>`);
    return `<div class="ocard">
      <b>${E(o.name_local)}</b><span class="t">${E(tierLabel(o.tier))}${o.city ? " · " + E(o.city) : ""}</span>
      ${o.note ? `<p>${E(o.note)}</p>` : ""}
      <p>${E(o.why)}${o.open_application ? " · <b>" + T("open_always") + "</b>" : ""}</p>
      ${links.length ? `<p>${links.join("")}</p>` : ""}
    </div>`;
  }).join("");
}

// data-i18n 이 붙은 노드의 글자를 지금 언어로 바꾼다
function applyStatic() {
  document.documentElement.lang = LANG === "zh_TW" ? "zh-Hant" : LANG;
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = T(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    el.placeholder = T(el.dataset.i18nPh);
  });
  document.querySelectorAll(".lang").forEach(b => {
    b.setAttribute("aria-pressed", String(b.dataset.lang === LANG));
  });
}

function setLang(lang) {
  if (!UI[lang] || lang === LANG) return;
  LANG = lang;
  try { localStorage.setItem("lang", lang); } catch (e) { /* 사파리 프라이빗 등 */ }
  applyStatic();
  paintMeta();
  render();
}

function paintMeta() {
  const off = DATA.offices, tracked = off.filter(o => o.status === "ok").length;
  document.getElementById("k-off").innerHTML = `${tracked}<small> / ${off.length}</small>`;
  document.getElementById("k-post").innerHTML = `${DATA.postings.length}`;
  const t = new Date(DATA.generated_at);
  const locale = { ko: "ko-KR", en: "en-US", zh_TW: "zh-TW" }[LANG] || "ko-KR";
  document.getElementById("k-time").textContent =
    t.toLocaleString(locale, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const un = off.filter(o => o.status !== "ok");
  document.getElementById("gap-h").textContent = T("gap_h", { n: un.length });
  document.getElementById("gaps").innerHTML = un.map(o =>
    `<span class="gapitem">${E(o.name_local)} <span style="opacity:.55">${o.country}</span></span>`).join("");
}

function toast(msg) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("on");
  setTimeout(() => el.classList.remove("on"), 6000);
}

async function poll() {
  try {
    const next = await fetchData();
    if (next.generated_at !== DATA.generated_at) {
      const before = DATA.postings.length;
      DATA = next;
      paintMeta();
      render();
      const diff = DATA.postings.length - before;
      toast(diff > 0 ? T("toast_new", { n: diff }) : T("toast_upd"));
    }
  } catch (e) { /* 일시적 실패는 무시하고 다음 주기에 다시 본다 */ }
}

(async function () {
  try {
    DATA = await fetchData();
  } catch (e) {
    document.getElementById("rows").innerHTML =
      `<p class="empty">${T("load_fail")}</p>`;
    return;
  }
  applyStatic();
  paintMeta();

  bind();
  render();

  // 1분마다 확인한다. 탭이 뒤에 있을 때는 쉬고, 다시 앞으로 오면 바로 한 번 본다.
  setInterval(() => { if (!document.hidden) poll(); }, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
