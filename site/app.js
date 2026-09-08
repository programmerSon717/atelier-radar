// data.json 을 읽어 화면을 그린다. HTML 에 데이터를 굽지 않으므로
// 봇이 새 데이터를 올리면 페이지를 다시 만들지 않아도 갱신된다.
const E = (s) => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const GATES = [
  { k: "open",     v: "--open",     t: "지원 가능",   d: "외국인 지원 가능이 적혀 있거나, 대만이라 국적 문제가 없다" },
  { k: "ask",      v: "--ask",      t: "문의 필요",   d: "외국인 채용 언급이 아예 없다. 담당자에게 먼저 물어봐야 한다" },
  { k: "native",   v: "--native",   t: "어학 장벽",   d: "TOPIK·JLPT 급수나 현지어가 필수로 적혀 있다" },
  { k: "domestic", v: "--domestic", t: "국내 유학생 전형", d: "외국인은 뽑지만 한국·일본 대학을 나온 유학생이 대상이다. 미국 졸업자는 해당 없음" },
  { k: "closed",   v: "--closed",   t: "지원 불가",   d: "외국인 불가 또는 비자 스폰서 불가가 명시돼 있다" },
];
const FLAG = { KR: "🇰🇷", JP: "🇯🇵", TW: "🇹🇼" };
const TRACK = { new_grad: "신입공채", intern: "인턴", intern_to_fulltime: "전환형 인턴",
                entry_level: "신입", year_round: "상시채용", other: "기타" };

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
    ["지금 바로 넣을 수 있는 곳부터 보고 싶다",
     `<b>지원 가능 ${gc.open || 0}건</b> — 대만 ${openTw} · 그 외 ${openOther}`],
    ["마감이 임박한 게 있는지 보고 싶다",
     soon.length ? `<b>2주 내 마감 ${soon.length}건</b> — ${soon.slice(0,3).map(s=>{
       const d=daysLeft(s.deadline, s.country);
       return `${E(s.company||s.office_name)} <b>${d===0?"오늘 마감":"D-"+d}</b>`;}).join(" · ")}` : "2주 내 마감 없음"],
    ["일단 인턴으로 발을 들이고 싶다", `<b>인턴·전환형 ${intern}건</b>`],
    ["한국어가 안 되는데 한국도 되나",
     `한국 공고 대부분은 외국인 채용을 <b>언급하지 않는다</b>. 그건 불가가 아니라 미확인이라, <b>문의 필요 ${gc.ask||0}건</b>은 메일 한 통으로 갈린다`],
    ["한국 대기업 외국인 전형은 왜 안 되나",
     `그쪽은 대개 <b>한국 대학을 나온 유학생</b>이 대상이고 TOPIK 급수를 요구한다. 미국 졸업자는 해당이 안 돼서 <b>국내 유학생 전형 ${gc.domestic||0}건</b>으로 따로 뺐다`],
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
  document.querySelector('.chip[data-v="live"]').textContent = `진행중 ${live}`;
  document.querySelector('.chip[data-v="past"]').textContent = `지난 공고 ${past}`;
  document.getElementById("count").textContent = `${list.length}건 표시`;
  syncClearButton();
  // 지난 공고 탭에서는 아카이브(가벼운 과거 기록)도 같이 보여준다
  if (state.view === "past") {
    const q2 = state.q.trim().toLowerCase();
    const arch = (DATA.archive || []).filter(a =>
      (state.country === "all" || a.country === state.country) &&
      (!q2 || `${a.company} ${a.title}`.toLowerCase().includes(q2)));
    list = list.concat(arch.map(a => ({
      ...a, archive: true, gate: "ask", gate_icon: "🗄",
      gate_label: "지난 기록", gate_reason: "마감된 공고의 요약 기록 (상세 없음)",
      track: "other", expired: true, deadline: a.deadline || a.posted_at,
      source_url: a.url, office_name: a.company, summary: "",
    })));
    list.sort((a, b) => String(b.deadline || b.posted_at || "")
      .localeCompare(String(a.deadline || a.posted_at || "")));
    document.getElementById("count").textContent = `${list.length}건 표시`;
  syncClearButton();
  }

  const rowsEl = document.getElementById("rows");
  if (!list.length) {
    rowsEl.innerHTML = `<p class="empty">${state.view === "past"
      ? "지난 공고가 아직 없다. 마감이 지나면 여기 쌓인다." : "조건에 맞는 공고가 없다. 필터를 넓혀 보라."}</p>`;
    return;
  }
  if (state.view === "past" && state.country === "all") {
    // 지난 공고는 나라별로 묶어서 본다 — 어느 나라가 언제 뽑았는지가 요점이다
    const order = ["KR", "JP", "TW"];
    const NAME = { KR: "🇰🇷 한국", JP: "🇯🇵 일본", TW: "🇹🇼 대만" };
    rowsEl.innerHTML = order.filter(c => list.some(p => p.country === c)).map(c => {
      const g = list.filter(p => p.country === c);
      const years = [...new Set(g.map(p => (p.deadline || "").slice(0, 4)).filter(Boolean))];
      return `<div class="grouphead">${NAME[c]} <span>${g.length}건${
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

function mailBlock(k) {
  const id = "m" + Math.random().toString(36).slice(2, 9);
  return `<details class="mail" open><summary>📨 문의 메일 초안 — 복사해서 보내면 된다</summary>
    <div class="jd" style="grid-template-columns:1fr">
      <div><h4>제목</h4><p>${E(k.subject)}</p></div>
      <div><h4>본문</h4><p id="${id}" style="white-space:pre-wrap">${E(k.body)}</p>
        <button class="chip" style="margin-top:9px" data-copy="${id}">본문 복사</button></div>
      ${k.hooks?.length ? `<div><h4>엮을 거리</h4><ul>${k.hooks.map(x=>`<li>${E(x)}</li>`).join("")}</ul></div>` : ""}
      ${k.ask_points?.length ? `<div><h4>꼭 물어볼 것</h4><ul>${k.ask_points.map(x=>`<li>${E(x)}</li>`).join("")}</ul></div>` : ""}
    </div></details>`;
}

function row(p) {
  if (p.archive) {
    const when = p.posted_at ? `게시 ${E(p.posted_at)}` : "";
    const dl = p.deadline && p.deadline !== p.posted_at ? ` · 마감 ${E(p.deadline)}` : "";
    return `<article class="row arch" style="--g:var(--closed)">
      <div class="stripe"></div><div class="rbody">
        <div class="rtop"><span class="gatechip">🗄 지난 기록</span>
          <span class="rtitle">${E(p.title)}</span>
          <span class="rfirm">${E(p.company || "")}</span></div>
        <div class="meta"><span>${when}${dl}</span><span>·</span><span>vmspace</span></div>
        <p style="margin:9px 0 0"><a class="src" href="${E(p.url)}" target="_blank" rel="noopener">공고 원문 →</a></p>
      </div></article>`;
  }
  const g = GATES.find(x => x.k === p.gate) || GATES[1];
  const dl = daysLeft(p.deadline, p.country);
  const meta = [
    FLAG[p.country] + " " + E(p.location || p.office_name),
    TRACK[p.track] || p.track,
    // 고용형태가 트랙과 같은 말이면 두 번 쓰지 않는다 ("인턴 · 인턴")
    p.employment_type && !new RegExp(TRACK[p.track] || "\u0000").test(p.employment_type)
      && !/^(intern(ship)?|인턴)$/i.test(p.employment_type.trim()) ? E(p.employment_type) : "",
    p.deadline ? `<span class="${dl !== null && dl <= 14 ? "due" : ""}">${p.expired ? "마감됨" : "마감"} ${E(p.deadline)}${dl !== null && dl >= 0 && dl <= 30 ? ` (D-${dl})` : ""}</span>` : "",
  ].filter(Boolean);

  const facts = [["고용형태", p.employment_type],
                 ["전형", p.process], ["언어 요건", p.language_required]]
    .filter(([, v]) => v).map(([k, v]) => `${E(k)}: ${E(v)}`);

  const jd = [
    bullets(p.responsibilities, "담당 업무"),
    bullets(p.qualifications, "자격 요건"),
    bullets(p.preferred, "우대 사항"),
    p.software?.length ? `<div><h4>요구 툴</h4><p>${E(p.software.join(" · "))}</p></div>` : "",
    facts.length ? `<div><h4>조건</h4><p>${facts.join("<br>")}</p></div>` : "",
    p.notes ? `<div><h4>확인 안 됨</h4><p>${E(p.notes)}</p></div>` : "",
    (p.contact_email || p.contact_phone || p.apply_how)
      ? `<div><h4>연락처 · 지원 방법</h4><p>${[
          p.contact_email ? `✉️ <a class="src" href="mailto:${E(p.contact_email)}">${E(p.contact_email)}</a>` : "",
          p.contact_phone ? `☎️ ${E(p.contact_phone)}` : "",
          p.apply_how ? E(p.apply_how) : ""].filter(Boolean).join("<br>")}</p></div>` : "",
    bullets(p.firm_projects, "이 사무소 프로젝트"),
    p.pay ? `<div><h4>연봉</h4><p>${[
        p.pay.stated ? `공고 명시: <b>${E(p.pay.stated)}</b>`
                     : (p.salary ? `공고 명시: ${E(p.salary)} <span style="opacity:.6">(금액 없음)</span>` : ""),
        p.pay.benchmark ? `업계 참고(신입): <b>${E(p.pay.benchmark.range)}</b>` : "",
        p.pay.benchmark?.note ? `<span style="opacity:.75">${E(p.pay.benchmark.note)}</span>` : "",
        p.pay.benchmark ? `<span style="opacity:.6">※ ${E(p.pay.benchmark.disclaimer)}</span>` : "",
      ].filter(Boolean).join("<br>")}</p></div>` : "",
    bullets(p.blockers_desc, "걸리는 조건"),
    bullets(p.soft_desc, "준비하면 넘는 조건"),
    bullets(p.met, "충족하는 조건"),
    bullets(p.unknowns, "확인이 필요한 것"),
  ].join("");

  return `<article class="row" style="--g:var(${g.v})">
    <div class="stripe"></div>
    <div class="rbody">
      <div class="rtop">
        <span class="gatechip">${p.gate_icon} ${E(g.t)}</span>
        ${fitChip(p)}
        <span class="rtitle">${E(p.title)}</span>
        <span class="rfirm">${E(p.company || p.office_name)}</span>
      </div>
      ${dl !== null && dl >= 0 && dl <= 3 ? `<p class="urgent">🚨 ${dl === 0 ? "오늘 마감" : "D-" + dl + " 마감 임박"}</p>` : ""}
      <div class="meta">${meta.map(m => `<span>${m}</span>`).join("<span>·</span>")}</div>
      <p class="why"><b>${E(p.gate_label)}</b> — ${E(p.gate_evidence || p.gate_reason)}</p>
      ${p.gate_action ? `<p class="act">👉 ${E(p.gate_action)}</p>` : ""}
      ${p.summary ? `<p class="why">${E(p.summary)}</p>` : ""}
      ${jd ? `<div class="jd">${jd}</div>` : `<p class="thin">이 공고는 원문 페이지에 상세 내용이 없다. 출처를 직접 확인해야 한다.</p>`}
      ${p.outreach ? mailBlock(p.outreach) : ""}
      <p style="margin:10px 0 0"><a class="src" href="${E(p.source_url)}" target="_blank" rel="noopener">공고 원문 →</a></p>
    </div></article>`;
}

// 지원 추천도 — 사무소 수준과 포트폴리오 접점으로 매긴다 (src/relevance.py: fit_grade)
const FIT = {
  recommend: { t: "추천", i: "\u{1F44D}", c: "#2f7d51" },
  neutral:   { t: "중립", i: "\u2796",    c: "#8a8a8a" },
  avoid:     { t: "비추천", i: "\u{1F44E}", c: "#a3452f" },
};

function fitChip(p) {
  const f = FIT[p.fit];
  if (!f) return "";
  const why = (p.fit_why || []).join(" · ");
  return `<span class="fitchip" style="--fc:${f.c}" title="${E(why)}">${f.i} ${f.t}</span>`;
}

function syncClearButton() {
  const on = state.country !== "all" || state.gates.size > 0 || state.q.trim() !== "";
  const el = document.getElementById("clear");
  if (el) el.hidden = !on;
}

function bind() {
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
    try { await navigator.clipboard.writeText(t); b.textContent = "복사됨 ✓"; }
    catch { b.textContent = "복사 실패 — 직접 선택하세요"; }
    setTimeout(() => (b.textContent = "본문 복사"), 2200);
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

function paintMeta() {
  const off = DATA.offices, tracked = off.filter(o => o.status === "ok").length;
  document.getElementById("k-off").innerHTML = `${tracked}<small> / ${off.length}</small>`;
  document.getElementById("k-post").innerHTML = `${DATA.postings.length}<small> 건</small>`;
  const t = new Date(DATA.generated_at);
  document.getElementById("k-time").textContent =
    t.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const un = off.filter(o => o.status !== "ok");
  document.getElementById("gap-h").textContent = `아직 추적하지 못하는 사무소 — ${un.length}곳`;
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
      toast(diff > 0 ? `새 공고 ${diff}건이 들어왔다` : "목록이 갱신됐다");
    }
  } catch (e) { /* 일시적 실패는 무시하고 다음 주기에 다시 본다 */ }
}

(async function () {
  try {
    DATA = await fetchData();
  } catch (e) {
    document.getElementById("rows").innerHTML =
      `<p class="empty">데이터를 불러오지 못했다. 잠시 뒤 새로고침해 보라.</p>`;
    return;
  }
  paintMeta();

  bind();
  render();

  // 1분마다 확인한다. 탭이 뒤에 있을 때는 쉬고, 다시 앞으로 오면 바로 한 번 본다.
  setInterval(() => { if (!document.hidden) poll(); }, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
