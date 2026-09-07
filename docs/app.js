// data.json 을 읽어 화면을 그린다. HTML 에 데이터를 굽지 않으므로
// 봇이 새 데이터를 올리면 페이지를 다시 만들지 않아도 갱신된다.
const E = (s) => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const GATES = [
  { k: "open",   v: "--open",   t: "지원 가능",     d: "외국인 지원 가능이 공고에 적혀 있거나, 대만이라 국적 문제가 없다" },
  { k: "ask",    v: "--ask",    t: "문의 필요",     d: "외국인 채용 언급이 아예 없다. 담당자에게 먼저 물어봐야 한다" },
  { k: "native", v: "--native", t: "언어 장벽",     d: "한국어·일본어가 필수로 적혀 있다. 지금은 어렵다" },
  { k: "closed", v: "--closed", t: "지원 불가",     d: "외국인 불가 또는 비자 스폰서 불가가 명시돼 있다" },
];
const FLAG = { KR: "🇰🇷", JP: "🇯🇵", TW: "🇹🇼" };
const TRACK = { new_grad: "신입공채", intern: "인턴", intern_to_fulltime: "전환형 인턴",
                entry_level: "신입", year_round: "상시채용", other: "기타" };

let DATA = null;
const state = { country: "all", gates: new Set(), q: "", hideExpired: true };

function daysLeft(d) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d || "")) return null;
  return Math.ceil((new Date(d + "T23:59:59") - new Date()) / 86400000);
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
  const soon = P.filter(p => { const d = daysLeft(p.deadline); return d !== null && d >= 0 && d <= 14; });
  const openTw = P.filter(p => p.gate === "open" && p.country === "TW").length;
  const openOther = P.filter(p => p.gate === "open" && p.country !== "TW").length;
  const intern = P.filter(p => /intern/.test(p.track) && p.gate !== "closed").length;
  const guide = [
    ["지금 바로 넣을 수 있는 곳부터 보고 싶다",
     `<b>지원 가능 ${gc.open || 0}건</b> — 대만 ${openTw} · 그 외 ${openOther}`],
    ["마감이 임박한 게 있는지 보고 싶다",
     soon.length ? `<b>2주 내 마감 ${soon.length}건</b> — ${E(soon.slice(0,2).map(s=>s.company||s.office_name).join(", "))}` : "2주 내 마감 없음"],
    ["일단 인턴으로 발을 들이고 싶다", `<b>인턴·전환형 ${intern}건</b>`],
    ["한국어가 안 되는데 한국도 되나",
     `한국 공고 대부분은 외국인 채용을 <b>언급하지 않는다</b>. 그건 불가가 아니라 미확인이라, <b>문의 필요 ${gc.ask||0}건</b>은 메일 한 통으로 갈린다`],
  ];
  document.getElementById("guide").innerHTML =
    guide.map(([q, a]) => `<tr><td>${E(q)}</td><td>${a}</td></tr>`).join("");

  // 필터
  const q = state.q.trim().toLowerCase();
  let list = P.filter(p =>
    (state.country === "all" || p.country === state.country) &&
    (state.gates.size === 0 || state.gates.has(p.gate)) &&
    (!state.hideExpired || !p.expired) &&
    (!q || [p.title, p.company, p.office_name, p.location, (p.software || []).join(" ")]
        .join(" ").toLowerCase().includes(q)));

  const rank = { open: 0, ask: 1, native: 2, closed: 3 };
  list.sort((a, b) => (rank[a.gate] - rank[b.gate])
    || ((daysLeft(a.deadline) ?? 9e3) - (daysLeft(b.deadline) ?? 9e3)));

  document.getElementById("count").textContent = `${list.length} / ${P.length}건`;
  document.getElementById("rows").innerHTML = list.length
    ? list.map(row).join("")
    : `<p class="empty">조건에 맞는 공고가 없다. 필터를 넓혀 보라.</p>`;
}

function bullets(items, label) {
  if (!items || !items.length) return "";
  return `<div><h4>${label}</h4><ul>${items.map(x => `<li>${E(x)}</li>`).join("")}</ul></div>`;
}

function row(p) {
  const g = GATES.find(x => x.k === p.gate) || GATES[1];
  const dl = daysLeft(p.deadline);
  const meta = [
    FLAG[p.country] + " " + E(p.location || p.office_name),
    TRACK[p.track] || p.track,
    // 고용형태가 트랙과 같은 말이면 두 번 쓰지 않는다 ("인턴 · 인턴")
    p.employment_type && !new RegExp(TRACK[p.track] || "\u0000").test(p.employment_type)
      && !/^(intern(ship)?|인턴)$/i.test(p.employment_type.trim()) ? E(p.employment_type) : "",
    p.deadline ? `<span class="${dl !== null && dl <= 14 ? "due" : ""}">${p.expired ? "마감됨" : "마감"} ${E(p.deadline)}${dl !== null && dl >= 0 && dl <= 30 ? ` (D-${dl})` : ""}</span>` : "",
  ].filter(Boolean);

  const facts = [["고용형태", p.employment_type], ["급여", p.salary],
                 ["전형", p.process], ["언어 요건", p.language_required]]
    .filter(([, v]) => v).map(([k, v]) => `${E(k)}: ${E(v)}`);

  const jd = [
    bullets(p.responsibilities, "담당 업무"),
    bullets(p.qualifications, "자격 요건"),
    bullets(p.preferred, "우대 사항"),
    p.software?.length ? `<div><h4>요구 툴</h4><p>${E(p.software.join(" · "))}</p></div>` : "",
    facts.length ? `<div><h4>조건</h4><p>${facts.join("<br>")}</p></div>` : "",
    p.notes ? `<div><h4>확인 안 됨</h4><p>${E(p.notes)}</p></div>` : "",
    p.labels?.length ? `<div><h4>판정 근거</h4><p>${p.labels.map(E).join("<br>")}</p></div>` : "",
  ].join("");

  return `<article class="row" style="--g:var(${g.v})">
    <div class="stripe"></div>
    <div class="rbody">
      <div class="rtop">
        <span class="gatechip">${p.gate_icon} ${E(g.t)}</span>
        <span class="rtitle">${E(p.title)}</span>
        <span class="rfirm">${E(p.company || p.office_name)}</span>
      </div>
      <div class="meta">${meta.map(m => `<span>${m}</span>`).join("<span>·</span>")}</div>
      <p class="why"><b>${E(p.gate_label)}</b> — ${E(p.gate_evidence || p.gate_reason)}</p>
      ${p.gate_action ? `<p class="act">👉 ${E(p.gate_action)}</p>` : ""}
      ${p.summary ? `<p class="why">${E(p.summary)}</p>` : ""}
      ${jd ? `<details><summary>상세 보기</summary><div class="jd">${jd}</div></details>` : ""}
      <p style="margin:10px 0 0"><a class="src" href="${E(p.source_url)}" target="_blank" rel="noopener">공고 원문 →</a></p>
    </div></article>`;
}

function bind() {
  document.getElementById("gates").addEventListener("click", e => {
    const b = e.target.closest(".gate"); if (!b) return;
    const k = b.dataset.g;
    state.gates.has(k) ? state.gates.delete(k) : state.gates.add(k);
    render();
  });
  document.querySelectorAll(".chip[data-c]").forEach(b => b.addEventListener("click", () => {
    state.country = b.dataset.c;
    document.querySelectorAll(".chip[data-c]").forEach(x =>
      x.setAttribute("aria-pressed", String(x === b)));
    render();
  }));
  const he = document.getElementById("hide-expired");
  he.addEventListener("click", () => {
    state.hideExpired = !state.hideExpired;
    he.setAttribute("aria-pressed", String(state.hideExpired));
    render();
  });
  document.getElementById("q").addEventListener("input", e => {
    state.q = e.target.value; render();
  });
}

(async function () {
  try {
    const r = await fetch("data.json?t=" + Date.now());
    DATA = await r.json();
  } catch (e) {
    document.getElementById("rows").innerHTML =
      `<p class="empty">데이터를 불러오지 못했다. 잠시 뒤 새로고침해 보라.</p>`;
    return;
  }
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

  bind();
  render();
})();
