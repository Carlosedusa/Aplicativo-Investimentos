"use strict";

const TABS = [["scanner", "Scanner"], ["ativo", "Ativo"], ["ticket", "Ordem"], ["carteira", "Carteira"]];
const state = { tab: "scanner", symbol: null, scan: null, asset: null, ticket: null, wallet: null, toast: null };
const view = document.getElementById("view");
const tabsEl = document.getElementById("tabs");

// ---------- utilidades
const usd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
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
const SETUPS = { breakout_resistance: "Rompeu a resistência", pullback_ma20: "Pullback na média de 20",
  support_bounce: "Repique no suporte" };
// Modo treino: ordens de teste ignoram o horário do mercado (as outras regras de Risco continuam).
const trainOn = () => store.get("train", "1") === "1";
function trainBox() {
  const box = h("input", { id: "train", type: "checkbox", style: "width:auto;min-height:0" });
  box.checked = trainOn();
  box.addEventListener("change", () => store.set("train", box.checked ? "1" : "0"));
  const status = h("p", { class: "muted" }, "Verificando o mercado…");
  api("/swing/market").then((m) => {
    status.textContent = m.open ? "Bolsa aberta agora: entradas liberadas."
      : m.reasons[0] + " Com o Modo treino ligado, você pode simular ordens mesmo assim.";
  }).catch(() => { status.textContent = ""; });
  return h("div", { class: "card stack" }, status,
    h("label", { style: "display:flex;gap:8px;align-items:center;font-size:14px" }, box, "Modo treino: ignorar o horário da bolsa"));
}
const ptReason = (r) => r;

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
  const fmt = (x) => String(x).replace(".", ",");
  const card = (x, withSetup) => {
    const o = x.odds, good = o.p_target >= o.breakeven;
    return h("button", { class: "hit", onclick: () => selectSymbol(x.symbol) },
      h("strong", null, x.symbol), h("span", { class: "num" }, money(x.price)),
      h("span", { class: "muted" }, withSetup ? x.setups.map((t) => SETUPS[t] || t).join(", ") : `${fmt(Math.abs(x.dist_sma20_pct))}% ${x.dist_sma20_pct >= 0 ? "acima" : "abaixo"} da média de 20`),
      h("span", { class: "num " + (o.avg_r >= 0 ? "gain" : "loss") }, (o.avg_r >= 0 ? "+" : "") + fmt(o.avg_r) + "R esperado"),
      h("span", { class: "full" }, h("span", { class: "chance " + (good ? "gain" : "loss") }, `Chance de chegar ao alvo: ${Math.round(o.p_target * 100)}%`,
        h("span", { class: "muted small" }, ` (equilíbrio ${Math.round(o.breakeven * 100)}%) · stop −${fmt(x.plan.risk_pct)}% · alvo +${fmt(x.plan.target_pct)}% (${fmt(x.plan.target_r)}R)`)),
        h("span", { class: "badge " + (x.recommend.ok ? "buy" : "no") }, x.recommend.ok ? "✔ Recomendada" : "✖ Não recomendada"),
        h("span", { class: "muted small block" }, x.recommend.reason)));
  };
  const bestCard = (s) => {
    const x = s.hits.find((y) => y.symbol === s.best);
    if (!x) return h("div", { class: "reco none" }, h("strong", null, "Nenhuma ação recomendada para comprar hoje"),
      h("p", null, s.hits.length ? "Há gatilho em " + s.hits.map((y) => y.symbol).join(", ") + ", mas a chance de chegar ao alvo não compensa o risco. Melhor esperar." : "Nenhuma ação em tendência de alta com gatilho de compra. Melhor esperar."));
    const o = x.odds, p = x.plan;
    return h("div", { class: "reco buy", role: "status" },
      h("span", { class: "tag" }, "RECOMENDADA PARA COMPRAR"),
      h("div", { class: "row" }, h("strong", { class: "big" }, x.symbol), h("span", { class: "num big" }, money(x.price))),
      h("p", null, x.setups.map((t) => SETUPS[t] || t).join(", ") + " · " + x.recommend.reason),
      h("div", { class: "row" }, h("span", null, "Stop"), h("span", { class: "num loss" }, money(p.stop))),
      h("div", { class: "row" }, h("span", null, "Alvo"), h("span", { class: "num gain" }, money(p.target))),
      h("div", { class: "row" }, h("span", null, "Chance de chegar ao alvo"), h("strong", { class: "num" }, Math.round(o.p_target * 100) + "% · " + (o.avg_r >= 0 ? "+" : "") + fmt(o.avg_r) + "R esperado")),
      h("button", { onclick: () => selectSymbol(x.symbol) }, "Ver plano e comprar " + x.symbol));
  };
  const show = () => {
    const s = state.scan;
    if (!s) return;
    out.replaceChildren(
      bestCard(s),
      h("p", { class: "muted" }, `${s.scanned} ações analisadas (${s.universe === "all" ? "toda a B3" : "Ibovespa"})${s.failed ? " (" + s.failed + " sem dados do Yahoo)" : ""}: ${s.uptrend} em tendência de alta, ${s.with_setup} com gatilho de compra hoje, ${s.with_plan} com plano de stop válido.`),
      s.hits.length ? h("h2", null, "Com gatilho de compra") : h("div", { class: "card" }, h("strong", null, "Nenhum gatilho de compra hoje."),
        h("p", { class: "muted" }, "É normal: o método só compra a favor da tendência e espera o preço recuar até a média de 20, tocar um suporte ou romper uma resistência. Veja abaixo quem está em tendência de alta e pode chegar lá.")),
      ...s.hits.map((x) => card(x, true)),
      s.watch && s.watch.length ? h("h2", null, "Para acompanhar (tendência de alta, sem gatilho ainda)") : null,
      ...(s.watch || []).map((x) => card(x, false)),
      h("p", { class: "muted small" }, "Chance = 2.000 simulações com o último ano do próprio ativo, até 15 pregões; stop abaixo do último pivô de baixa, alvo na próxima resistência. Não é previsão."));
  };
  const run = async (kind) => {
    const t0 = Date.now(), label = kind === "all" ? "toda a B3" : "o Ibovespa";
    const msg = h("p", { class: "spinner", role: "status" }, `Varrendo ${label}…`);
    out.replaceChildren(brainSvg(), msg);
    let prog = "";
    const timer = setInterval(async () => {
      try { const p = await api("/swing/scan/progress"); if (p.total) prog = ` ${p.done} de ${p.total} ações ·`; } catch { /* segue sem o contador */ }
      msg.textContent = `Varrendo ${label}…${prog} ${Math.round((Date.now() - t0) / 1000)} s`;
    }, 1000);
    try {
      const { task_id } = await api("/swing/scan", { method: "POST", body: { universe: kind } });
      state.scan = await waitTask(task_id);
      show();
    } catch (e) { out.replaceChildren(errorBox(e)); }
    finally { clearInterval(timer); }
  };
  show();
  return h("section", { class: "stack" },
    h("h1", null, "Scanner · B3"),
    h("p", { class: "muted" }, "Seguimento de tendência (swing): operações de alguns dias a poucas semanas em ações da B3. É uma lista para estudar, não para comprar."),
    trainBox(),
    h("button", { onclick: () => run("ibov") }, "Varrer o Ibovespa (rápido)"),
    h("button", { class: "ghost", onclick: () => run("all") }, "Varrer toda a B3 (lento, 1 a 3 min)"),
    out);
}

function selectSymbol(sym) {
  state.symbol = sym; state.asset = null; state.ticket = null;
  go("ativo");
}

// ---------- gráfico de velas (5 min) com entrada, stop e alvo; zoom e arrasto
function chartCard(symbol, levels, title, interval = "5m") {
  const NS = "http://www.w3.org/2000/svg";
  const el = (t, at, txt) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(at)) e.setAttribute(k, v); if (txt != null) e.textContent = txt; return e; };
  const W = 360, H = 260, PR = 54, PT = 8, PB = 8, PW = W - PR, PH = H - PT - PB;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": interval === "1d" ? "Gráfico de velas diárias com entrada, stop e alvo" : "Gráfico de velas de 5 minutos com entrada, stop e alvo" });
  const stamp = h("p", { class: "muted" }, "Carregando gráfico…");
  const msg = h("div");
  let candles = [], view = null; // view = {x0,x1,y0,y1} em coordenadas de dados (x = nº da vela, y = preço)
  const lv = [levels.target, levels.entry, levels.stop, levels.support].filter((v) => typeof v === "number");

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
    if (interval === "1d") {  // médias móveis de 20 e 50 dias
      [[20, "ma20"], [50, "ma50"]].forEach(([n, cls]) => {
        const pts = [];
        for (let i = n - 1; i < candles.length; i++) {
          if (i < x0 - 1 || i > x1 + 1) continue;
          let sum = 0; for (let k = i - n + 1; k <= i; k++) sum += candles[k].c;
          pts.push(`${X(i).toFixed(1)},${Y(sum / n).toFixed(1)}`);
        }
        if (pts.length > 1) g.append(el("polyline", { points: pts.join(" "), class: "ma " + cls }));
      });
    }
    [[levels.target, "Alvo", "lt"], [levels.resistance, "Resist.", "lr"], [levels.entry, "Entrada", "le"], [levels.support, "Suporte", "lsu"], [levels.stop, "Stop", "ls"]].forEach(([v, name, cls]) => {
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
  const box = h("div", { class: "card stack" }, h("h2", null, title || (interval === "1d" ? "Gráfico · velas diárias" : "Gráfico · velas de 5 min")), tools, msg, svg, stamp,
    h("p", { class: "muted small" }, "Arraste para mover (tempo e preço). Roda do mouse ou pinça dá zoom; Shift + roda amplia só o preço. Toque duplo volta ao padrão."));

  let timer = null, started = false;
  let busy = false;
  const load = async () => {
    if (started && !box.isConnected) { clearInterval(timer); started = false; return; }
    if (busy) return; // não empilha pedidos se a rede estiver lenta
    busy = true;
    try {
      const d = await api("/candles/" + symbol + "?interval=" + interval);
      const wasEnd = view && view.x1 >= candles.length; // se estava no fim, acompanha as velas novas
      const shift = d.candles.length - candles.length;
      candles = d.candles; msg.replaceChildren();
      if (view && wasEnd && shift > 0) { view.x0 += shift; view.x1 += shift; }
      draw();
      const last = candles[candles.length - 1];
      stamp.textContent = `Atualiza a cada ${interval === "1d" ? 10 : 1} s · último preço ${money(last && last.c)} · ${new Date().toLocaleTimeString("pt-BR")}`;
    } catch (e) { if (!candles.length) msg.replaceChildren(errorBox(e)); else stamp.textContent = "Sem atualização agora; tentando de novo… (" + (e.message || e) + ")"; }
    finally { busy = false; }
  };
  setTimeout(() => { started = true; load(); timer = setInterval(load, interval === "1d" ? 10000 : 1000); }, 0);
  return box;
}

// ---------- ativo
function assetView() {
  if (!state.symbol) return emptyView("Escolha uma ação", "Rode o Scanner e toque em uma ação da lista.");
  const out = h("div", { class: "stack" }, h("p", { class: "spinner" }, "Carregando " + state.symbol + "…"));
  const fmt = (x) => String(x).replace(".", ",");
  const draw = () => {
    const a = state.asset, p = a.plan, o = a.odds;
    out.replaceChildren(
      h("div", { class: "reco " + (a.recommend.ok ? "buy" : "none"), role: "status" },
        h("span", { class: "tag" }, a.recommend.ok ? "RECOMENDADA PARA COMPRAR" : "NÃO RECOMENDADA AGORA"), h("p", null, a.recommend.reason)),
      h("div", { class: "card stack" }, h("div", { class: "row" }, h("strong", null, a.setups.length ? a.setups.map((t) => SETUPS[t] || t).join(", ") : "Sem sinal agora"), h("span", { class: "num" }, money(a.price))),
        h("p", { class: a.trend.up ? "gain" : "loss" }, a.trend.up ? "Tendência de alta: preço acima da média de 50, média de 20 acima da de 50 e a de 50 subindo." : "Sem tendência de alta clara: o método só compra a favor da tendência."),
        h("p", { class: "muted" }, `Média 20: ${money(a.trend.sma20)} · Média 50: ${money(a.trend.sma50)} · Suporte: ${money(a.support)} · Resistência: ${money(a.resistance)}`),
        h("p", { class: "muted" }, `RSI ${fmt(a.rsi)} · ATR (variação diária típica) ${money(a.atr)} · liquidez ${money(a.turnover)}/dia`)),
      chartCard(state.symbol, p ? { entry: p.entry, stop: p.stop, target: p.target, support: p.support, resistance: p.resistance } : { support: a.support, resistance: a.resistance }, "Gráfico · velas diárias + médias de 20 e 50", "1d"),
      p ? h("div", { class: "card" }, h("h2", null, "Plano (swing, até " + p.horizon_days + " pregões)"), h("div", { class: "ladder" },
        h("div", { class: "step target" }, h("span", null, `Alvo: ${p.target_basis} (${fmt(p.target_r)}R, +${fmt(p.target_pct)}%)`), h("span", { class: "num" }, money(p.target))),
        h("div", { class: "step entry" }, h("span", null, "Entrada"), h("span", { class: "num" }, money(p.entry))),
        h("div", { class: "step stop" }, h("span", null, `Stop: abaixo do ${p.stop_basis} (−${fmt(p.risk_pct)}%)`), h("span", { class: "num" }, money(p.stop)))),
        h("p", { class: "muted" }, `Risco de ${money(p.risk)} por ação. Se não bater stop nem alvo, a ordem de teste sai ao fim de ${p.horizon_days} pregões. O stop é fixo (não acompanha a alta).`)) : h("div", { class: "error" }, "Sem plano: o último pivô de baixa está longe demais (risco alto para o ganho) ou faltam dados."),
      o && h("div", { class: "card stack" }, h("h2", null, "Chance (simulação do último ano)"),
        h("div", { class: "row" }, h("span", null, "Chegar ao alvo"), h("strong", { class: "num " + (o.p_target >= o.breakeven ? "gain" : "loss") }, Math.round(o.p_target * 100) + "%")),
        h("div", { class: "row" }, h("span", null, "Bater o stop"), h("span", { class: "num" }, Math.round(o.p_stop * 100) + "%")),
        h("div", { class: "row" }, h("span", null, `Nenhum dos dois em ${o.horizon_days} pregões`), h("span", { class: "num" }, Math.round(o.p_time * 100) + "%")),
        h("div", { class: "row" }, h("span", null, "Retorno esperado"), h("span", { class: "num " + (o.avg_r >= 0 ? "gain" : "loss") }, (o.avg_r >= 0 ? "+" : "") + fmt(o.avg_r) + "R")),
        h("p", { class: "muted small" }, `Para a conta compensar com alvo de ${fmt(p.target_r)}R, a chance precisa passar de ${Math.round(o.breakeven * 100)}%. Simulação com ${o.replays} caminhos; não é previsão: balanços e notícias podem mudar tudo.`)),
      p && h("button", { onclick: () => go("ticket") }, "Montar ordem de teste"));
  };
  (async () => {
    try { state.asset = await api("/swing/asset/" + state.symbol); draw(); }
    catch (e) { out.replaceChildren(errorBox(e)); }
  })();
  return h("section", { class: "stack" }, h("h1", null, state.symbol), out);
}

// ---------- ordem de teste
function ticketView() {
  if (!state.symbol) return emptyView("Sem ação escolhida", "Abra uma ação do Scanner primeiro.");
  const maxLoss = h("input", { id: "maxloss", type: "number", inputmode: "decimal", min: "1", value: store.get("maxloss", "100") });
  const out = h("div", { class: "stack" });
  let sending = false;
  const body = (extra) => ({ symbol: state.symbol, max_loss: Number(maxLoss.value), train: trainOn(), ...extra });

  const draw = () => {
    const t = state.ticket;
    if (!t) return;
    const ok = t.risk.verdict === "PASS", o = t.risk.order;
    const confirmBtn = h("button", { id: "confirm", disabled: !ok || sending, onclick: async () => {
      sending = true; confirmBtn.disabled = true;
      try {
        await api("/swing/orders", { method: "POST", body: body({ client_order_id: t.clientOrderId, confirm: true }) });
        state.toast = "Ordem de teste enviada."; state.ticket = null; state.wallet = null;
        go("carteira");
      } catch (e) {
        sending = false;
        out.append(errorBox(e));
        confirmBtn.disabled = !ok;
      }
    } }, "Confirmar ordem de teste");
    out.replaceChildren(
      ok ? h("div", { class: "card stack" },
        h("div", { class: "row" }, h("strong", null, `Comprar ${o.qty} ${o.symbol}`), h("span", { class: "num" }, money(o.entry))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Stop"), h("span", { class: "num loss" }, money(o.stop))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Alvo"), h("span", { class: "num gain" }, money(o.target))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Perda máxima no stop"), h("span", { class: "num" }, money(o.max_loss))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Ganho no alvo"), h("span", { class: "num" }, money(o.target_gain))),
        h("div", { class: "row" }, h("span", { class: "muted" }, "Valor investido"), h("span", { class: "num" }, money(o.cost))),
        h("p", { class: "muted small" }, `A posição fica aberta de um dia para o outro, até bater stop ou alvo, ou por no máximo ${o.horizon_days} pregões.`)) : null,
      ok ? h("div", { class: "ok" }, h("strong", null, "Aprovado pelo Risco"), ...t.risk.warnings.map((w) => h("p", { class: "muted" }, w)))
         : h("div", { class: "error", role: "alert" }, h("strong", null, "Bloqueado pelo Risco"), ...t.risk.reasons.map((r) => h("p", null, ptReason(r)))),
      chartCard(state.symbol, t.risk.order ? { entry: o.entry, stop: o.stop, target: o.target } : {}, "Gráfico · velas diárias + médias de 20 e 50", "1d"),
      confirmBtn);
  };
  const calc = async () => {
    store.set("maxloss", maxLoss.value);
    out.replaceChildren(h("p", { class: "spinner" }, "Calculando…"));
    try {
      const risk = await api("/swing/order/preview", { method: "POST", body: body({ client_order_id: "preview" }) });
      state.ticket = { risk, clientOrderId: uid() };
      draw();
    } catch (e) { out.replaceChildren(errorBox(e)); }
  };
  if (state.ticket) draw();
  return h("section", { class: "stack" }, h("h1", null, "Ordem de teste · " + state.symbol),
    h("p", { class: "muted" }, "Dinheiro de teste. O app calcula quantas ações comprar para que a perda no stop não passe do limite."),
    trainBox(),
    h("label", null, "Perda máxima por operação (R$)", maxLoss),
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
    if (chartId !== p.id) { chartId = p.id; chart = chartCard(p.symbol, { entry: p.entry, stop: p.stop, target: p.target }, `Gráfico · ${p.symbol} (diário)`, "1d"); }
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
          h("span", { class: "num " + cls(p.open_pnl) }, money(p.open_pnl))))) : h("p", { class: "muted" }, "Nenhuma posição. Rode o Scanner e monte uma ordem de teste.")),
      chartFor(positions),
      h("div", { class: "card" }, h("h2", null, "Histórico"),
        history.length ? h("ul", { class: "plain" }, history.map((t) => h("li", { class: "row" },
          h("span", null, h("strong", null, `${t.qty} ${t.symbol}`), h("span", { class: "muted" }, " fechou no " + ({ stop: "stop", target: "alvo", eod: "fim do dia", prazo: "prazo" })[t.reason])),
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
  const views = { scanner: scannerView, ativo: assetView, ticket: ticketView, carteira: walletView };
  try { view.replaceChildren(views[state.tab]()); }
  catch (e) { view.replaceChildren(h("h1", null, "Ops"), errorBox(new Error("Erro na tela: " + (e && e.message ? e.message : e)))); }
}

// Erro inesperado em qualquer lugar: mostra na tela (em vez de ficar em branco) para dar para diagnosticar.
function showCrash(msg) {
  const box = document.getElementById("crash") || h("div", { id: "crash", class: "error", role: "alert", style: "margin:16px" });
  box.textContent = "Erro inesperado: " + msg + " (tire um print e me envie)";
  if (!box.isConnected) document.body.prepend(box);
}
window.addEventListener("error", (e) => showCrash(e.message));
window.addEventListener("unhandledrejection", (e) => showCrash(e.reason && e.reason.message ? e.reason.message : String(e.reason)));

render();
