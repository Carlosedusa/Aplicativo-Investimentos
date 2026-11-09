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

async function waitTask(id, maxSeconds = 480) {
  for (let i = 0; i < Math.ceil(maxSeconds / 1.2); i++) {
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
const SETUPS = { breakout_20d: "Rompeu máxima de 20 dias", bull_flag: "Bandeira de alta", reclaim_ma20: "Retomou a média de 20",
  oversold: "Sobrevendida (RSI<30)", oversold_bounce: "Rebote após sobrevenda", orb: "Rompimento da abertura" };
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
  const oddsOf = {};   // símbolo -> chance calculada
  const pending = new Set(); // símbolos ainda sendo calculados
  const fmt = (x) => String(x).replace(".", ",");
  const row = (hit) => {
    const o = oddsOf[hit.symbol];
    const line2 = hit.at ? "rompeu às " + hit.at : "fechou em " + (hit.close_date || "—") + (hit.rsi != null ? " · RSI " + fmt(hit.rsi) : "");
    const right = hit.pct_over != null ? h("span", { class: "num gain" }, "+" + fmt(hit.pct_over) + "%") : h("span", { class: "muted" }, (hit.setups || []).map((s) => SETUPS[s] || s).join(", "));
    let chance;
    if (!o) chance = pending.has(hit.symbol) ? h("span", { class: "muted small" }, "Calculando chance…") : h("span", { class: "muted small" }, "Toque para ver o plano e simular");
    else if (o.error) chance = h("span", { class: "muted small", title: o.error }, "Chance indisponível: " + String(o.error).slice(0, 80));
    else {
      const p = o.p_target, good = p >= o.breakeven;
      chance = h("span", { class: "chance " + (good ? "gain" : "loss") }, `Chance de chegar ao alvo: ${Math.round(p * 100)}%`,
        h("span", { class: "muted small" }, ` (equilíbrio ${Math.round(o.breakeven * 100)}%)`));
    }
    return h("button", { class: "hit", onclick: () => { selectSymbol(hit.symbol); } },
      h("strong", null, hit.symbol), h("span", { class: "num" }, money(hit.price)),
      h("span", { class: "muted" }, line2), right,
      h("span", { class: "full" }, chance));
  };
  const ranked = () => {
    const hits = rankHits(state.scan.hits).slice(0, 40);
    const top = hits.slice(0, 15).sort((a, b) => ((oddsOf[b.symbol] || {}).p_target ?? -1) - ((oddsOf[a.symbol] || {}).p_target ?? -1));
    return [...top, ...hits.slice(15)];
  };
  const show = () => {
    const s = state.scan;
    if (!s) return;
    out.replaceChildren(
      h("p", { class: "muted" }, `${s.counts ? s.counts.scanned : s.scanned} gráficos analisados, ${s.hits.length} com o padrão.`),
      h("p", { class: "muted small" }, "A chance vem de 2.000 simulações com os últimos 60 dias do próprio ativo (stop na faixa inicial ou 1%, alvo 2R). Não é previsão. Os 15 primeiros são calculados e sobem pela chance."),
      ...ranked().map(row));
  };
  // Calcula em lotes de 3, dois lotes ao mesmo tempo: a tela vai preenchendo e um ativo lento não trava os outros.
  const loadOdds = async () => {
    const hits = rankHits(state.scan.hits).slice(0, 15);
    hits.forEach((x) => { if (!oddsOf[x.symbol]) pending.add(x.symbol); });
    const batches = [];
    for (let i = 0; i < hits.length; i += 3) batches.push(hits.slice(i, i + 3).filter((x) => pending.has(x.symbol)));
    const refresh = () => { if (state.tab === "scanner" && out.isConnected) show(); };
    const doBatch = async (b) => {
      if (!b.length) return;
      try {
        const { task_id } = await api("/odds", { method: "POST", body: { hits: b.map((x) => ({ symbol: x.symbol, price: x.price,
          ...(x.or_high != null ? { or_high: x.or_high, or_low: x.or_low, bar_index: x.bar_index } : {}) })) } });
        Object.assign(oddsOf, (await waitTask(task_id, 90)).odds);
      } catch (e) { b.forEach((x) => { oddsOf[x.symbol] = { error: e.message }; }); }
      b.forEach((x) => pending.delete(x.symbol));
      refresh();
    };
    const lane = async () => { while (batches.length) await doBatch(batches.shift()); };
    refresh();
    await Promise.all([lane(), lane()]);
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
      loadOdds();
    } catch (e) { out.replaceChildren(errorBox(e)); }
    finally { clearInterval(timer); }
  };
  if (state.scan) { show(); loadOdds(); }
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

// ---------- gráfico de velas (5 min) com entrada, stop e alvo; zoom e arrasto
function chartCard(symbol, levels, title) {
  const NS = "http://www.w3.org/2000/svg";
  const el = (t, at, txt) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(at)) e.setAttribute(k, v); if (txt != null) e.textContent = txt; return e; };
  const W = 360, H = 260, PR = 54, PT = 8, PB = 8, PW = W - PR, PH = H - PT - PB;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": "Gráfico de velas de 5 minutos com entrada, stop e alvo" });
  const stamp = h("p", { class: "muted" }, "Carregando gráfico…");
  const msg = h("div");
  let candles = [], view = null; // view = {x0,x1,y0,y1} em coordenadas de dados (x = nº da vela, y = preço)
  const lv = [levels.target, levels.entry, levels.stop].filter((v) => typeof v === "number");

  const fit = () => {
    const n = candles.length, from = Math.max(0, n - 78); // ~1 pregão
    const sl = candles.slice(from);
    const lo = Math.min(...sl.map((c) => c.l), ...lv), hi = Math.max(...sl.map((c) => c.h), ...lv), pad = (hi - lo) * 0.06 || 1;
    view = { x0: from - 0.5, x1: n + 3, y0: lo - pad, y1: hi + pad };
  };
  const draw = () => {
    if (!candles.length) return;
    if (!view) fit();
    const { x0, x1, y0, y1 } = view;
    const X = (i) => ((i - x0) / (x1 - x0)) * PW, Y = (v) => PT + PH * (1 - (v - y0) / (y1 - y0));
    const bw = Math.max(1.5, (PW / (x1 - x0)) * 0.6);
    const clip = el("clipPath", { id: "clip-" + symbol }); clip.append(el("rect", { x: 0, y: 0, width: PW, height: H }));
    const g = el("g", { "clip-path": `url(#clip-${symbol})` });
    candles.forEach((c, i) => {
      if (i < x0 - 1 || i > x1 + 1) return;
      const up = c.c >= c.o, cls = up ? "cu" : "cd", x = X(i);
      g.append(el("line", { x1: x, x2: x, y1: Y(c.h), y2: Y(c.l), class: cls }));
      g.append(el("rect", { x: x - bw / 2, width: bw, y: Math.min(Y(c.o), Y(c.c)), height: Math.max(1, Math.abs(Y(c.o) - Y(c.c))), class: cls + " body" }));
    });
    const parts = [el("defs", {}), g];
    parts[0].append(clip);
    [[levels.target, "Alvo", "lt"], [levels.entry, "Entrada", "le"], [levels.stop, "Stop", "ls"]].forEach(([v, name, cls]) => {
      if (typeof v !== "number") return;
      const yy = Math.max(PT + 10, Math.min(H - PB - 10, Y(v))), out = Y(v) < PT || Y(v) > H - PB;
      if (!out) parts.push(el("line", { x1: 0, x2: PW, y1: yy, y2: yy, class: "lvl " + cls }));
      parts.push(el("text", { x: PW + 3, y: yy - 2, class: "lbl " + cls }, (out ? (Y(v) < PT ? "▲ " : "▼ ") : "") + name));
      parts.push(el("text", { x: PW + 3, y: yy + 9, class: "lbl " + cls }, v.toFixed(2)));
    });
    for (let k = 0; k <= 4; k++) { const v = y0 + ((y1 - y0) * k) / 4; parts.push(el("text", { x: PW + 3, y: Y(v) + 3, class: "lbl ax" }, k % 2 ? "" : v.toFixed(2))); }
    svg.replaceChildren(...parts);
  };

  // zoom (roda do mouse, pinça, botões) e arrasto nos dois eixos
  const toData = (sx, sy) => ({ x: view.x0 + (sx / PW) * (view.x1 - view.x0), y: view.y1 - ((sy - PT) / PH) * (view.y1 - view.y0) });
  const zoom = (f, sx, sy, only) => {
    if (!view) return;
    const a = toData(sx, sy);
    if (only !== "y" && (view.x1 - view.x0) * f >= 5 && (view.x1 - view.x0) * f <= 2000) { view.x0 = a.x - (a.x - view.x0) * f; view.x1 = a.x + (view.x1 - a.x) * f; }
    if (only !== "x") { view.y0 = a.y - (a.y - view.y0) * f; view.y1 = a.y + (view.y1 - a.y) * f; }
    draw();
  };
  const pt = (e) => { const r = svg.getBoundingClientRect(); return [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H]; };
  const ptrs = new Map(); let pinch = 0;
  svg.addEventListener("wheel", (e) => { e.preventDefault(); const [sx, sy] = pt(e); zoom(e.deltaY < 0 ? 0.85 : 1 / 0.85, sx, sy, e.shiftKey ? "y" : null); }, { passive: false });
  svg.addEventListener("pointerdown", (e) => { svg.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, pt(e)); pinch = 0; });
  svg.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId) || !view) return;
    const prev = ptrs.get(e.pointerId), cur = pt(e); ptrs.set(e.pointerId, cur);
    if (ptrs.size >= 2) {
      const [p, q] = [...ptrs.values()], d = Math.hypot(p[0] - q[0], p[1] - q[1]);
      if (pinch) zoom(pinch / d, (p[0] + q[0]) / 2, (p[1] + q[1]) / 2);
      pinch = d; return;
    }
    const dx = ((cur[0] - prev[0]) / PW) * (view.x1 - view.x0); view.x0 -= dx; view.x1 -= dx;
    const dy = ((cur[1] - prev[1]) / PH) * (view.y1 - view.y0); view.y0 += dy; view.y1 += dy;
    draw();
  });
  const up = (e) => { ptrs.delete(e.pointerId); pinch = 0; };
  svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
  svg.addEventListener("dblclick", () => { fit(); draw(); });

  const btn = (label, name, fn) => h("button", { class: "ghost mini", "aria-label": name, title: name, onclick: fn }, label);
  const tools = h("div", { class: "tools" },
    btn("+", "Aproximar", () => zoom(0.7, PW / 2, H / 2)), btn("−", "Afastar", () => zoom(1 / 0.7, PW / 2, H / 2)),
    btn("↕+", "Ampliar só o preço", () => zoom(0.7, PW / 2, H / 2, "y")), btn("↕−", "Reduzir só o preço", () => zoom(1 / 0.7, PW / 2, H / 2, "y")),
    btn("⟲", "Voltar ao padrão", () => { fit(); draw(); }));
  const box = h("div", { class: "card stack" }, h("h2", null, title || "Gráfico · velas de 5 min"), tools, msg, svg, stamp,
    h("p", { class: "muted small" }, "Arraste para mover (tempo e preço). Roda do mouse ou pinça dá zoom; Shift + roda amplia só o preço. Toque duplo volta ao padrão."));

  let timer = null, started = false;
  let busy = false;
  const load = async () => {
    if (started && !box.isConnected) { clearInterval(timer); started = false; return; }
    if (busy) return; // não empilha pedidos se a rede estiver lenta
    busy = true;
    try {
      const d = await api("/candles/" + symbol);
      const wasEnd = view && view.x1 >= candles.length; // se estava no fim, acompanha as velas novas
      const shift = d.candles.length - candles.length;
      candles = d.candles; msg.replaceChildren();
      if (view && wasEnd && shift > 0) { view.x0 += shift; view.x1 += shift; }
      draw();
      const last = candles[candles.length - 1];
      stamp.textContent = `Atualiza a cada 1 s · último preço ${money(last && last.c)} · ${new Date().toLocaleTimeString("pt-BR")}`;
    } catch (e) { if (!candles.length) msg.replaceChildren(errorBox(e)); else stamp.textContent = "Sem atualização agora; tentando de novo…"; }
    finally { busy = false; }
  };
  setTimeout(() => { started = true; load(); timer = setInterval(load, 1000); }, 0);
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
  // Um único gráfico fixo; com várias posições, escolha qual acompanhar.
  let picked = null, chart = null, chartId = null;
  const chartFor = (positions) => {
    if (!positions.length) { chart = chartId = null; return null; }
    const p = positions.find((x) => x.id === picked) || positions[0];
    if (chartId !== p.id) { chartId = p.id; chart = chartCard(p.symbol, { entry: p.entry, stop: p.stop, target: p.target }, `Gráfico · ${p.symbol} (5 min)`); }
    const pick = positions.length > 1 && h("div", { class: "chips" }, positions.map((x) => h("button", {
      class: x.id === p.id ? "mini" : "ghost mini", onclick: () => { picked = x.id; draw(); } }, x.symbol)));
    return h("div", { class: "stack" }, pick, chart);
  };
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
      chartFor(positions),
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
  const live = setInterval(() => { if (!out.isConnected) clearInterval(live); else load(); }, 10000);
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

render();
