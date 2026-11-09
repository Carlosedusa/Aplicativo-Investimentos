"use strict";

const TABS = [["scanner", "Scanner"], ["ativo", "Ativo"], ["simular", "Simular"], ["ticket", "Ordem"], ["carteira", "Carteira"]];
const state = { tab: "scanner", symbol: null, scan: null, asset: null, tm: null, ticket: null, wallet: null, toast: null };
const view = document.getElementById("view");
const tabsEl = document.getElementById("tabs");

// ---------- utilidades
const usd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" });
const pct = (x) => (x * 100).toFixed(1).replace(".", ",") + "%";
const money = (n) => (n == null ? "—" : usd.format(n));
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k)));
  return el;
}
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } },
};
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));

class ApiError extends Error {
  constructor(message, status, extra) { super(message); this.status = status; this.extra = extra || {}; }
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      method: opts.method || "GET",
      headers: { Authorization: "Bearer " + store.get("token", ""), "Content-Type": "application/json" },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError("Sem conexão com o servidor. Confira se ele está ligado.", 0);
  }
  let data = null;
  try { data = await res.json(); } catch { /* corpo vazio */ }
  if (res.status === 401) { store.set("token", ""); render(); throw new ApiError("Token inválido.", 401); }
  if (!res.ok) {
    const d = data && data.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? "Dados inválidos." : "Erro " + res.status;
    throw new ApiError(msg, res.status, data || {});
  }
  return data;
}

async function waitTask(id) {
  for (let i = 0; i < 400; i++) {
    const t = await api("/tasks/" + id);
    if (t.status === "done") return t.result;
    if (t.status === "error") throw new ApiError(t.error || "A tarefa falhou.", 502);
    await new Promise((r) => setTimeout(r, 1200));
  }
  throw new ApiError("A tarefa demorou demais.", 504);
}

const errorBox = (e) => h("div", { class: "error", role: "alert" }, e.message || String(e));

// ---------- login
function loginView(msg) {
  const input = h("input", { id: "token", type: "password", autocomplete: "off", placeholder: "Cole o token do servidor" });
  const out = h("div");
  const go = async () => {
    store.set("token", input.value.trim());
    try { await api("/auth/check"); render(); }
    catch (e) { view.replaceChildren(loginView(e)); }
  };
  return h("section", { class: "stack" },
    h("h1", null, "Entrar"),
    h("p", { class: "muted" }, "Digite o token que você definiu no servidor (API_TOKEN)."),
    h("label", null, "Token", input),
    out, msg && errorBox(msg),
    h("button", { onclick: go }, "Entrar"));
}

// ---------- scanner
// Maior oportunidade primeiro: no rompimento, quanto acima da faixa (pct_over); no pré-mercado, mantém a ordem do servidor.
function rankHits(hits) {
  const score = (x) => (typeof x.pct_over === "number" ? x.pct_over : null);
  if (!hits.some((x) => score(x) != null)) return hits;
  return [...hits].sort((a, b) => (score(b) ?? -Infinity) - (score(a) ?? -Infinity) || a.symbol.localeCompare(b.symbol));
}

// Modo treino: ordens de teste ignoram o horário do mercado (as outras regras de Risco continuam).
const trainOn = () => store.get("train", "1") === "1";
function trainBox() {
  const box = h("input", { id: "train", type: "checkbox", style: "width:auto;min-height:0" });
  box.checked = trainOn();
  box.addEventListener("change", () => store.set("train", box.checked ? "1" : "0"));
  const status = h("p", { class: "muted" }, "Verificando o mercado…");
  api("/market/status").then((m) => {
    status.textContent = m.open ? "Mercado aberto agora: entradas liberadas."
      : "Mercado fechado agora em Nova York (abre 10:30 em Brasília, seg. a sex.). Com o Modo treino ligado, você pode simular ordens mesmo assim.";
  }).catch(() => { status.textContent = ""; });
  return h("div", { class: "card stack" }, status,
    h("label", { style: "display:flex;gap:8px;align-items:center;font-size:14px" }, box, "Modo treino: ignorar o horário do mercado"));
}
const ptReason = (r) => r.startsWith("window:") ? "Fora do horário de entrada do mercado (Nova York). Ligue o Modo treino para simular." : r;

function brainSvg() {
  const NS = "http://www.w3.org/2000/svg";
  const el = (t, at) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(at)) e.setAttribute(k, v); return e; };
  const svg = el("svg", { viewBox: "0 0 200 140", class: "brain", role: "img", "aria-label": "Cérebro analisando o mercado" });
  // contorno (2 hemisférios) + sulcos + sinapses
  const paths = [
    "M100 14 C78 4 52 14 48 36 C30 38 20 56 28 72 C20 88 32 106 50 106 C56 124 82 130 100 120",
    "M100 14 C122 4 148 14 152 36 C170 38 180 56 172 72 C180 88 168 106 150 106 C144 124 118 130 100 120",
    "M100 14 L100 120",
    "M56 50 C70 44 82 54 92 48", "M144 50 C130 44 118 54 108 48",
    "M44 76 C60 70 72 84 90 76", "M156 76 C140 70 128 84 110 76",
    "M62 98 C74 90 84 102 94 94", "M138 98 C126 90 116 102 106 94",
  ];
  paths.forEach((d, i) => svg.append(el("path", { d, class: "bl", style: `animation-delay:${(i * 0.18).toFixed(2)}s` })));
  [[56,50],[92,48],[44,76],[90,76],[62,98],[94,94],[144,50],[108,48],[156,76],[110,76],[138,98],[106,94],[100,30],[100,104]]
    .forEach(([x, y], i) => svg.append(el("circle", { cx: x, cy: y, r: 3, class: "bn", style: `animation-delay:${(i * 0.13).toFixed(2)}s` })));
  return svg;
}
function scannerView() {
  const out = h("div", { class: "stack" });
  const show = () => {
    const s = state.scan;
    if (!s) return;
    out.replaceChildren(
      h("p", { class: "muted" }, `${s.counts ? s.counts.scanned : s.scanned} gráficos analisados, ${s.hits.length} com o padrão.`),
      ...rankHits(s.hits).slice(0, 40).map((hit) => h("button", { class: "hit", onclick: () => { selectSymbol(hit.symbol); } },
        h("strong", null, hit.symbol), h("span", { class: "num" }, money(hit.price)),
        h("span", { class: "muted" }, "rompeu às " + hit.at), h("span", { class: "num gain" }, "+" + String(hit.pct_over).replace(".", ",") + "%"))));
  };
  const run = async (mode, popular) => {
    const t0 = Date.now();
    const msg = h("p", { class: "spinner", role: "status" }, "Varrendo o mercado…");
    out.replaceChildren(brainSvg(), msg);
    const timer = setInterval(() => { msg.textContent = `Varrendo o mercado… ${Math.round((Date.now() - t0) / 1000)} s`; }, 1000);
    try {
      const { task_id } = await api("/scan/" + mode, { method: "POST", body: { popular } });
      state.scan = await waitTask(task_id);
      show();
    } catch (e) { out.replaceChildren(errorBox(e)); }
    finally { clearInterval(timer); }
  };
  show();
  return h("section", { class: "stack" },
    h("h1", null, "Scanner"),
    h("p", { class: "muted" }, "Procura gráficos que cumprem uma regra. É uma lista para estudar, não para comprar."),
    trainBox(),
    h("button", { onclick: () => run("daily", true) }, "Pré-mercado (ações populares, rápido)"),
    h("button", { class: "ghost", onclick: () => run("orb", true) }, "Rompimento da abertura (populares)"),
    h("button", { class: "ghost", onclick: () => run("daily", false) }, "Pré-mercado completo (lento, vários minutos)"),
    out);
}

function selectSymbol(sym) {
  state.symbol = sym; state.asset = null; state.tm = null; state.ticket = null;
  go("ativo");
}

// ---------- gráfico de velas (15 min) com entrada, stop e alvo
function candleChart(candles, { entry, stop, target }) {
  const NS = "http://www.w3.org/2000/svg";
  const el = (t, at, txt) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(at)) e.setAttribute(k, v); if (txt) e.textContent = txt; return e; };
  const W = 360, H = 220, PR = 54, PT = 8, PB = 8;
  const levels = [entry, stop, target].filter((v) => typeof v === "number");
  const lo = Math.min(...candles.map((c) => c.l), ...levels), hi = Math.max(...candles.map((c) => c.h), ...levels);
  const pad = (hi - lo) * 0.06 || 1, min = lo - pad, max = hi + pad;
  const y = (v) => PT + (H - PT - PB) * (1 - (v - min) / (max - min));
  const step = (W - PR) / candles.length, bw = Math.max(2, step * 0.6);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Gráfico de velas de 15 minutos com entrada, stop e alvo" });
  candles.forEach((c, i) => {
    const x = step * i + step / 2, up = c.c >= c.o, cls = up ? "cu" : "cd";
    svg.append(el("line", { x1: x, x2: x, y1: y(c.h), y2: y(c.l), class: cls }));
    svg.append(el("rect", { x: x - bw / 2, width: bw, y: Math.min(y(c.o), y(c.c)), height: Math.max(1, Math.abs(y(c.o) - y(c.c))), class: cls + " body" }));
  });
  [[target, "Alvo", "lt"], [entry, "Entrada", "le"], [stop, "Stop", "ls"]].forEach(([v, name, cls]) => {
    if (typeof v !== "number") return;
    svg.append(el("line", { x1: 0, x2: W - PR, y1: y(v), y2: y(v), class: "lvl " + cls }));
    svg.append(el("text", { x: W - PR + 3, y: y(v) - 2, class: "lbl " + cls }, name));
    svg.append(el("text", { x: W - PR + 3, y: y(v) + 9, class: "lbl " + cls }, v.toFixed(2)));
  });
  return svg;
}

function chartCard(symbol, levels) {
  const box = h("div", { class: "card stack" }, h("h2", null, "Gráfico · velas de 15 min"), h("p", { class: "muted" }, "Carregando gráfico…"));
  api("/candles/" + symbol).then((d) => {
    box.replaceChildren(h("h2", null, "Gráfico · velas de 15 min"), candleChart(d.candles, levels),
      h("p", { class: "muted" }, "Linha verde: alvo (ganho). Linha vermelha: stop (perda). Linha escura: entrada."));
  }).catch((e) => box.replaceChildren(h("h2", null, "Gráfico · velas de 15 min"), errorBox(e)));
  return box;
}

// ---------- ativo
function assetView() {
  if (!state.symbol) return emptyView("Escolha um ativo", "Rode o Scanner e toque em um ativo da lista.");
  const out = h("div", { class: "stack" }, h("p", { class: "spinner" }, "Carregando " + state.symbol + "…"));
  const draw = () => {
    const a = state.asset;
    const status = a.entry.status === "triggered" ? "Entrada disparada" : a.entry.status === "waiting" ? "Esperando o gatilho" : a.entry.status;
    const p = a.plan;
    out.replaceChildren(
      h("div", { class: "card stack" }, h("div", { class: "row" }, h("strong", null, status), h("span", { class: "num" }, money(a.entry.trigger && a.entry.trigger.price))),
        h("p", { class: "muted" }, a.entry.reason)),
      p && chartCard(state.symbol, { entry: p.entry, stop: p.stop, target: p.target }),
      p ? h("div", { class: "card" }, h("h2", null, "Plano de saída"), h("div", { class: "ladder" },
        h("div", { class: "step target" }, h("span", null, "Alvo (" + p.target_r + "R)"), h("span", { class: "num" }, money(p.target))),
        h("div", { class: "step entry" }, h("span", null, "Entrada"), h("span", { class: "num" }, money(p.entry))),
        h("div", { class: "step stop" }, h("span", null, "Stop (" + ({ or_mid: "meio da faixa inicial", or_low: "mínima da faixa inicial" }[p.stop_rule] || p.stop_rule) + ")"), h("span", { class: "num" }, money(p.stop)))),
        h("p", { class: "muted" }, `Risco de ${money(p.risk_per_share)} por ação. Sair até as ${p.flat_by}.`)) : h("div", { class: "error" }, a.planError || "Sem plano de saída."),
      h("div", { class: "card" }, h("h2", null, "Notícias"),
        a.news.items.length ? h("ul", { class: "plain" }, a.news.items.map((n) => h("li", null, h("a", { href: n.link || "#", target: "_blank", rel: "noopener" }, n.title), h("p", { class: "muted" }, n.source)))) : h("p", { class: "muted" }, "Nenhuma notícia nova nas últimas horas.")),
      p && h("button", { onclick: () => go("simular") }, "Simular chances"));
  };
  (async () => {
    try {
      const sym = state.symbol;
      const [entry, news] = await Promise.all([api("/entry/" + sym), api("/news?tickers=" + sym + "&hours=24")]);
      let plan = null, planError = null;
      try { plan = await api("/exit/plan", { method: "POST", body: {} }); } catch (e) { planError = e.message; }
      state.asset = { entry, news, plan, planError };
      draw();
    } catch (e) { out.replaceChildren(errorBox(e)); }
  })();
  return h("section", { class: "stack" }, h("h1", null, state.symbol), out);
}

// ---------- time machine
function simularView() {
  if (!state.asset || !state.asset.plan) return emptyView("Sem plano para simular", "Abra um ativo com plano de saída primeiro.");
  const out = h("div", { class: "stack" });
  const draw = () => {
    const r = state.tm, mc = r.mc, hist = r.history;
    out.replaceChildren(
      h("div", { class: "card stack" },
        h("h2", null, `${mc.replays.toLocaleString("pt-BR")} sessões simuladas`),
        h("div", { class: "ruler", role: "img", "aria-label": `Stop primeiro ${pct(mc.p_stop)}, em aberto ${pct(mc.p_neither)}, alvo primeiro ${pct(mc.p_target)}` },
          h("span", { class: "s", style: `flex:${mc.p_stop}` }),
          h("span", { class: "n", style: `flex:${mc.p_neither}` }),
          h("span", { class: "t", style: `flex:${mc.p_target}` })),
        h("div", { class: "legend" },
          h("span", { class: "loss" }, "Stop primeiro " + pct(mc.p_stop)),
          h("span", null, "Em aberto " + pct(mc.p_neither)),
          h("span", { class: "gain" }, "Alvo primeiro " + pct(mc.p_target)))),
      h("div", { class: "card stack" }, h("h2", null, "Veredito"),
        h("p", null, `Em ${hist.triggered} operações passadas com a mesma regra, o resultado médio foi ${String(hist.avg_R).replace(".", ",")}R por operação.`),
        h("p", { class: "muted", lang: "en" }, r.verdict),
        h("p", { class: "muted" }, `Nas ${hist.sessions} sessões passadas, o padrão apareceu ${hist.triggered} vezes: alvo ${hist.target}, stop ${hist.stop}, sem resolver ${hist.close}.`)),
      h("button", { onclick: () => go("ticket") }, "Montar ordem de teste"));
  };
  if (state.tm) draw();
  else {
    out.replaceChildren(h("p", { class: "spinner" }, "Simulando 10.000 sessões…"));
    (async () => {
      try {
        const { task_id } = await api("/timemachine/run", { method: "POST", body: {} });
        state.tm = await waitTask(task_id);
        if (state.tab === "simular") draw();
      } catch (e) { out.replaceChildren(errorBox(e)); }
    })();
  }
  return h("section", { class: "stack" }, h("h1", null, "Simulação · " + state.symbol), out);
}

// ---------- ordem de teste
function ticketView() {
  if (!state.asset || !state.asset.plan) return emptyView("Sem plano para a ordem", "Abra um ativo com plano de saída primeiro.");
  const budget = h("input", { id: "budget", type: "number", inputmode: "decimal", min: "1", value: store.get("budget", "5000") });
  const maxLoss = h("input", { id: "maxloss", type: "number", inputmode: "decimal", min: "1", value: store.get("maxloss", "50") });
  const out = h("div", { class: "stack" });
  let sending = false;

  const draw = () => {
    const t = state.ticket;
    if (!t) return;
    const ok = t.risk.verdict === "PASS";
    const confirmBtn = h("button", { id: "confirm", disabled: !ok || sending, onclick: async () => {
      sending = true; confirmBtn.disabled = true;
      try {
        await api("/paper/orders", { method: "POST", body: { client_order_id: t.clientOrderId, symbol: t.order.symbol,
          qty: t.order.qty, stop: t.order.stop, target: t.order.target, confirm: true, train: trainOn() } });
        state.toast = "Ordem de teste enviada."; state.ticket = null; state.wallet = null;
        go("carteira");
      } catch (e) {
        sending = false;
        out.append(errorBox(e));
        confirmBtn.disabled = !ok;
      }
    } }, "Confirmar ordem de teste");
    out.replaceChildren(
      h("div", { class: "card stack" },
        h("div", { class: "row" }, h("strong", null, `Comprar ${t.order.qty} ${t.order.symbol}`), h("span", { class: "num" }, money(t.order.entry))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Stop"), h("span", { class: "num loss" }, money(t.order.stop))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Alvo"), h("span", { class: "num gain" }, money(t.order.target))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Perda máxima no stop"), h("span", { class: "num" }, money(t.order.max_loss)))),
      ok ? h("div", { class: "ok" }, h("strong", null, "Aprovado pelo Risco"), ...t.risk.warnings.map((w) => h("p", { class: "muted" }, w)))
         : h("div", { class: "error", role: "alert" }, h("strong", null, "Bloqueado pelo Risco"), ...t.risk.reasons.map((r) => h("p", null, ptReason(r)))),
      chartCard(t.order.symbol, { entry: t.order.entry, stop: t.order.stop, target: t.order.target }),
      confirmBtn);
  };
  const calc = async () => {
    store.set("budget", budget.value); store.set("maxloss", maxLoss.value);
    out.replaceChildren(h("p", { class: "spinner" }, "Calculando…"));
    try {
      const order = await api("/budget/size", { method: "POST", body: { budget: Number(budget.value), max_loss: Number(maxLoss.value) } });
      const risk = await api("/risk/check?train=" + trainOn(), { method: "POST" });
      state.ticket = { order, risk, clientOrderId: uid() };
      draw();
    } catch (e) { out.replaceChildren(errorBox(e)); }
  };
  if (state.ticket) draw();
  return h("section", { class: "stack" },
    h("h1", null, "Ordem de teste"),
    h("label", null, "Caixa de teste (US$)", budget),
    h("label", null, "Perda máxima por operação (US$)", maxLoss),
    h("button", { class: "ghost", onclick: calc }, "Calcular tamanho"),
    out);
}

// ---------- carteira
function walletView() {
  const out = h("div", { class: "stack" });
  const draw = () => {
    const { account: a, positions, history } = state.wallet;
    const cls = (n) => (n > 0 ? "gain" : n < 0 ? "loss" : "");
    out.replaceChildren(
      h("div", { class: "card stack" }, h("h2", null, "Patrimônio de teste"), h("p", { class: "big num" }, money(a.equity)),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Caixa"), h("span", { class: "num" }, money(a.cash))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Resultado aberto"), h("span", { class: "num " + cls(a.open_pnl) }, money(a.open_pnl))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Resultado fechado"), h("span", { class: "num " + cls(a.closed_pnl) }, money(a.closed_pnl)))),
      h("div", { class: "card" }, h("h2", null, "Posições abertas"),
        positions.length ? h("ul", { class: "plain" }, positions.map((p) => h("li", { class: "row" },
          h("span", null, h("strong", null, `${p.qty} ${p.symbol}`), h("span", { class: "muted" }, " a " + money(p.entry))),
          h("span", { class: "num " + cls(p.open_pnl) }, money(p.open_pnl))))) : h("p", { class: "muted" }, "Nenhuma posição. Monte uma ordem de teste a partir do Scanner.")),
      h("div", { class: "card" }, h("h2", null, "Histórico"),
        history.length ? h("ul", { class: "plain" }, history.map((t) => h("li", { class: "row" },
          h("span", null, h("strong", null, `${t.qty} ${t.symbol}`), h("span", { class: "muted" }, " fechou no " + ({ stop: "stop", target: "alvo", eod: "fim do dia" })[t.reason])),
          h("span", { class: "num " + cls(t.pnl) }, money(t.pnl))))) : h("p", { class: "muted" }, "Nenhuma operação fechada ainda.")));
  };
  const load = async () => {
    try {
      const [account, positions, history] = await Promise.all([api("/paper/account"), api("/paper/positions"), api("/paper/history")]);
      state.wallet = { account, positions, history };
      if (state.tab === "carteira") draw();
    } catch (e) { out.replaceChildren(errorBox(e)); }
  };
  if (state.wallet) draw(); else out.replaceChildren(h("p", { class: "spinner" }, "Carregando…"));
  load();
  const toast = state.toast; state.toast = null;
  return h("section", { class: "stack" }, h("h1", null, "Carteira"),
    toast && h("div", { class: "ok toast", role: "status" }, toast),
    h("button", { class: "ghost", onclick: load }, "Atualizar"), out);
}

function emptyView(title, text) {
  return h("section", { class: "stack" }, h("h1", null, title), h("p", { class: "muted" }, text));
}

// ---------- navegação
function go(tab) { state.tab = tab; render(); window.scrollTo(0, 0); }

function render() {
  tabsEl.replaceChildren();
  if (!store.get("token", "")) { tabsEl.hidden = true; view.replaceChildren(loginView()); return; }
  tabsEl.hidden = false;
  for (const [id, label] of TABS) {
    tabsEl.append(h("button", { "aria-current": state.tab === id ? "page" : null, onclick: () => go(id) }, label));
  }
  const views = { scanner: scannerView, ativo: assetView, simular: simularView, ticket: ticketView, carteira: walletView };
  view.replaceChildren(views[state.tab]());
}

setInterval(() => { if (state.tab === "carteira" && store.get("token", "")) render(); }, 30000);
render();
