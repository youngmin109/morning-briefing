/* boan-news 대시보드 — 빌드 없는 vanilla JS. data/latest.json + data/history/*.json을 읽는다. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const fmtNum = (n) => Number(n).toLocaleString("ko-KR");

/* 피드/LLM 응답은 신뢰할 수 없는 입력이므로 innerHTML 주입 전 반드시 이스케이프 */
function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
function safeUrl(u) {
  try {
    return /^https?:$/.test(new URL(String(u ?? "")).protocol) ? u : "#";
  } catch { return "#"; }
}
const starsOf = (v) => "★".repeat(Math.min(5, Math.max(1, Math.floor(Number(v) || 3)))) +
                      "☆".repeat(5 - Math.min(5, Math.max(1, Math.floor(Number(v) || 3))));

function changeClass(pct) { return pct > 0 ? "up" : pct < 0 ? "down" : "flat"; }
function changeText(pct) {
  const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "─";
  return `${arrow} ${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function marketCard(item, unit) {
  return `<div class="market-card">
    <div class="label">${esc(item.label)}</div>
    <div class="price">${fmtNum(item.price)}${unit}</div>
    <div class="change ${changeClass(item.change_pct)}">${changeText(item.change_pct)}</div>
  </div>`;
}

/* 오늘의 명언 — 날짜를 시드로 하루 한 개가 고정되어 매일 바뀜 */
const QUOTES = [
  { text: "우리를 죽이지 못하는 것은 우리를 더 강하게 만든다.", author: "니체" },
  { text: "음악이 없는 삶은 잘못된 삶일 것이다.", author: "니체" },
  { text: "네가 심연을 오래 들여다볼수록, 심연 또한 너를 들여다본다.", author: "니체" },
  { text: "살아야 할 '왜'를 아는 사람은 그 어떤 '어떻게'도 견딜 수 있다.", author: "니체" },
  { text: "사실은 없다. 해석만 있을 뿐이다.", author: "니체" },
  { text: "춤추는 별을 낳으려면, 자기 안에 여전히 혼돈이 있어야 한다.", author: "니체" },
  { text: "우리가 삶을 사랑하는 것은 살아온 데 익숙해서가 아니라, 사랑하는 데 익숙하기 때문이다.", author: "니체" },
  { text: "불행한 결혼을 만드는 것은 사랑의 부족이 아니라 우정의 부족이다.", author: "니체" },
  { text: "결혼할 때 스스로에게 물어라. 늙어서까지 이 사람과 대화가 잘 통할 것 같은가?", author: "니체" },
  { text: "성숙함이란 어린아이가 놀 때 가지는 진지함을 다시 발견하는 것이다.", author: "니체" },
  { text: "모든 문제는 대인관계의 문제다.", author: "알프레드 아들러" },
  { text: "비판하지 말고, 원망하지 말고, 불평하지 말라.", author: "데일 카네기" },
  { text: "사람의 이름은 그 사람에게 세상의 어떤 말보다 달콤하고 중요한 소리다.", author: "데일 카네기" },
  { text: "내가 만나는 모든 사람은 어떤 면에서 나보다 뛰어나다. 나는 그 점을 그들에게서 배운다.", author: "랄프 왈도 에머슨" },
  { text: "사랑은 서로를 응시하는 것이 아니라, 함께 같은 방향을 바라보는 것이다.", author: "생텍쥐페리" },
  { text: "남에게 대접받고 싶은 대로 남을 대접하지 마라. 사람의 취향은 저마다 다르다.", author: "조지 버나드 쇼" },
  { text: "자기 기분을 전환하는 가장 빠른 길은, 다른 누군가의 기분을 전환시켜주려 애쓰는 것이다.", author: "마크 트웨인" },
];

function renderQuote(data) {
  const dateStr = String(data?.date || new Date().toISOString().slice(0, 10));
  const q = QUOTES[[...dateStr].reduce((a, c) => a + c.charCodeAt(0), 0) % QUOTES.length];
  $("#quote-text").textContent = `❝ ${q.text} ❞`;
  $("#quote-author").textContent = `— ${q.author}`;
}

function renderMarket(data) {
  const m = data.market || {};
  const cards = [];
  (m.kr?.indices || []).forEach((i) => cards.push(marketCard(i, "")));
  (m.kr?.stocks || []).forEach((i) => cards.push(marketCard(i, "원")));
  (m.us?.stocks || []).forEach((i) => cards.push(marketCard(i, "$")));
  (m.us?.fx || []).forEach((i) => cards.push(marketCard(i, "원")));
  (m.crypto || []).forEach((i) => cards.push(marketCard(i, "원")));

  if (!cards.length) { $("#market-section").classList.add("hidden"); return; }
  $("#market-grid").innerHTML = cards.join("");
  $("#market-time").textContent = m.collected_at ? `· ${m.collected_at.slice(11, 16)} KST 기준` : "";

  const mb = data.market_briefing || {};
  if (mb.headline || mb.commentary) {
    $("#market-briefing").classList.remove("hidden");
    $("#market-briefing").innerHTML =
      `<div class="headline">🧭 ${esc(mb.headline || "")}</div><p>${esc(mb.commentary || "")}</p>`;
  } else {
    $("#market-briefing").classList.add("hidden");
  }

  const study = mb.study_note || {};
  if (study.term && (study.simple_explanation || study.market_connection)) {
    $("#stock-study").classList.remove("hidden");
    $("#stock-study").innerHTML = `
      <div class="study-header">
        <div class="study-title">📚 오늘의 주식 1분 과외</div>
        <span class="study-term-badge">${esc(study.term)}</span>
      </div>
      <div class="study-desc">${esc(study.simple_explanation || "")}</div>
      ${study.market_connection ? `<div class="study-connection">🔍 <strong>오늘의 시장 연결:</strong> ${esc(study.market_connection)}</div>` : ""}
      ${study.action_tip ? `<div class="study-tip">💡 <strong>실전 체크:</strong> ${esc(study.action_tip)}</div>` : ""}
    `;
  } else {
    $("#stock-study").classList.add("hidden");
  }

  $("#market-section").classList.remove("hidden");
}

let currentFilter = "전체";

function renderFilters(articles) {
  const cats = ["전체", ...new Set(articles.map((a) => a.category))];
  $("#filters").innerHTML = cats
    .map((c) => `<button data-cat="${esc(c)}" class="${c === currentFilter ? "active" : ""}">${esc(c)}</button>`)
    .join("");
  document.querySelectorAll("#filters button").forEach((btn) =>
    btn.addEventListener("click", () => {
      currentFilter = btn.dataset.cat;
      renderArticles(currentData);
    })
  );
}

function renderArticles(data) {
  const all = data.articles || [];
  const shown = all.filter((a) => currentFilter === "전체" || a.category === currentFilter);
  renderFilters(all);
  $("#articles").innerHTML = shown.map((a) => `
    <article class="article-card" style="border-left-color: var(--accent)">
      <div class="cat-row">
        <span class="badge ${esc(a.category)}">${esc(a.category)}</span>
        <span class="stars">${starsOf(a.importance)}</span>
      </div>
      <h3 class="article-title"><a href="${safeUrl(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a></h3>
      <ul>${(a.summary || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
      ${(a.tags || []).length ? `<div class="tags">${a.tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div>` : ""}
      ${a.tech_insight ? `<div class="insight">🛡️ ${esc(a.tech_insight)}</div>` : ""}
      <div class="article-footer"><span>📡 ${esc(a.source || "")}</span><a href="${safeUrl(a.link)}" target="_blank" rel="noopener">원문 보기 →</a></div>
    </article>`).join("");
  $("#news-section").classList.remove("hidden");
}

function renderTrending(data) {
  const list = data.trending || [];
  if (!list.length) { $("#trending-section").classList.add("hidden"); return; }
  $("#trending-list").innerHTML = list.map((r) => `
    <li>
      <div>
        <a class="repo" href="${safeUrl(r.url)}" target="_blank" rel="noopener">${esc(r.repo)}</a>
        ${r.description ? `<span class="desc">${esc(r.description)}</span>` : ""}
      </div>
      <span class="meta">★${fmtNum(r.total_stars)} (+${fmtNum(r.period_stars)})</span>
    </li>`).join("");
  $("#trending-section").classList.remove("hidden");
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

async function loadDate(dateStr) {
  try {
    const path = dateStr ? `data/history/${dateStr}.json` : "data/latest.json";
    const data = await fetchJson(path);
    currentData = data;
    document.querySelectorAll("#archive-nav button").forEach((b) =>
      b.classList.toggle("active", b.dataset.date === (dateStr || ""))
    );
    renderQuote(data);
    renderMarket(data);
    renderArticles(data);
    renderTrending(data);
  } catch (e) {
    console.error(e);
  }
}

let currentData = null;

async function init() {
  try {
    const idx = await fetchJson("data/index.json").catch(() => ({ dates: [] }));
    const nav = $("#archive-nav");
    const dates = idx.dates || [];
    nav.innerHTML =
      `<button data-date="" class="active">최신</button>` +
      dates.map((d) => `<button data-date="${esc(d)}">${esc(d.slice(5))}</button>`).join("");
    nav.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => loadDate(b.dataset.date))
    );
    await loadDate("");
    $("#loading").classList.add("hidden");
  } catch (e) {
    $("#loading").textContent =
      "데이터를 불러올 수 없습니다. 아직 첫 자동 실행이 완료되지 않았을 수 있습니다.";
    console.error(e);
  }
}

init();
