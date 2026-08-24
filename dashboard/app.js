/* boan-news 대시보드 — 빌드 없는 vanilla JS. data/latest.json + data/history/*.json을 읽는다. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const fmtNum = (n) => Number(n).toLocaleString("ko-KR");

function changeClass(pct) { return pct > 0 ? "up" : pct < 0 ? "down" : "down"; }
function changeText(pct) {
  const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "─";
  return `${arrow} ${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function marketCard(item, unit) {
  return `<div class="market-card">
    <div class="label">${item.label}</div>
    <div class="price">${fmtNum(item.price)}${unit}</div>
    <div class="change ${changeClass(item.change_pct)}">${changeText(item.change_pct)}</div>
  </div>`;
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
      `<div class="headline">🧭 ${mb.headline || ""}</div><p>${mb.commentary || ""}</p>`;
  }
  $("#market-section").classList.remove("hidden");
}

let currentFilter = "전체";

function renderFilters(articles) {
  const cats = ["전체", ...new Set(articles.map((a) => a.category))];
  $("#filters").innerHTML = cats
    .map((c) => `<button data-cat="${c}" class="${c === currentFilter ? "active" : ""}">${c}</button>`)
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
        <span class="badge ${a.category}">${a.category}</span>
        <span class="stars">${"★".repeat(a.importance || 3)}${"☆".repeat(5 - (a.importance || 3))}</span>
      </div>
      <h3 class="article-title"><a href="${a.link}" target="_blank" rel="noopener">${a.title}</a></h3>
      <ul>${(a.summary || []).map((s) => `<li>${s}</li>`).join("")}</ul>
      ${(a.tags || []).length ? `<div class="tags">${a.tags.map((t) => `<span class="tag">#${t}</span>`).join("")}</div>` : ""}
      ${a.tech_insight ? `<div class="insight">🛡️ ${a.tech_insight}</div>` : ""}
      <div class="article-footer"><span>📡 ${a.source || ""}</span><a href="${a.link}" target="_blank" rel="noopener">원문 보기 →</a></div>
    </article>`).join("");
  $("#news-section").classList.remove("hidden");
}

function renderTrending(data) {
  const list = data.trending || [];
  if (!list.length) { $("#trending-section").classList.add("hidden"); return; }
  $("#trending-list").innerHTML = list.map((r) => `
    <li>
      <div>
        <a class="repo" href="${r.url}" target="_blank" rel="noopener">${r.repo}</a>
        ${r.description ? `<span class="desc">${r.description}</span>` : ""}
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
    const dates = (idx.dates || []).slice(0, 14);
    nav.innerHTML =
      `<button data-date="" class="active">최신</button>` +
      dates.map((d) => `<button data-date="${d}">${d.slice(5)}</button>`).join("");
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
