"""Swing trade em ações: tendência por médias móveis, suportes/resistências e stop em pivôs.

Estratégia (compra, alguns dias a poucas semanas):
  * Tendência de alta: preço acima da média de 50, média de 20 acima da de 50 e a de 50 subindo.
  * Entradas: pullback na média de 20, repique no suporte (pivô de baixa) ou rompimento da resistência (pivô de alta).
  * Stop logo abaixo do último pivô de baixa; alvo na próxima resistência (pivô de alta) ou, sem ela, em 3R.
Chance = simulação (bootstrap) com as variações diárias do próprio ativo no último ano. Não é previsão."""
import random

HORIZON = 15          # pregões (~3 semanas)
PIVOT_N = 3           # um pivô precisa de 3 candles de cada lado
STOP_BUFFER_ATR = 0.25
MIN_RISK_ATR, MAX_RISK_ATR = 1.0, 3.5
MIN_TARGET_R, FALLBACK_R = 1.5, 3.0
REPLAYS = 2000
MIN_BARS = 80
MIN_TURNOVER = 2_000_000.0   # R$ negociados por dia (média de 20 pregões)


def sma(c: list[float], n: int, back: int = 0) -> float:
    end = len(c) - back
    return sum(c[end - n:end]) / n


def rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag, al = (ag * (n - 1) + max(d, 0)) / n, (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def atr(bars: list[dict], n: int = 14) -> float:
    trs = [max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"])) for p, b in zip(bars, bars[1:])]
    return sum(trs[-n:]) / min(n, len(trs))


def pivots(bars: list[dict], n: int = PIVOT_N) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """(pivôs de alta, pivôs de baixa) confirmados: máxima/mínima maior/menor que as n velas de cada lado."""
    highs, lows = [], []
    for i in range(n, len(bars) - n):
        win = bars[i - n:i + n + 1]
        if bars[i]["h"] == max(b["h"] for b in win) and sum(1 for b in win if b["h"] == bars[i]["h"]) == 1:
            highs.append((i, bars[i]["h"]))
        if bars[i]["l"] == min(b["l"] for b in win) and sum(1 for b in win if b["l"] == bars[i]["l"]) == 1:
            lows.append((i, bars[i]["l"]))
    return highs, lows


def trend(c: list[float]) -> dict:
    s20, s50, s50_prev = sma(c, 20), sma(c, 50), sma(c, 50, 5)
    return {"up": c[-1] > s50 and s20 > s50 and s50 > s50_prev, "sma20": round(s20, 2), "sma50": round(s50, 2)}


def levels(bars: list[dict], price: float) -> dict:
    """Suporte (pivô de baixa mais recente abaixo do preço) e resistências (pivôs de alta acima), da mais próxima."""
    highs, lows = pivots(bars)
    sup = [v for _, v in reversed(lows) if v < price]
    res = sorted({v for _, v in highs if v > price * 1.002})
    return {"support": sup[0] if sup else None, "resistances": res, "last_pivot_high": highs[-1][1] if highs else None}


def setups(bars: list[dict], t: dict, lv: dict, a: float) -> list[str]:
    if not t["up"]:
        return []
    c, last = [b["c"] for b in bars], bars[-1]
    out = []
    ph = lv["last_pivot_high"]
    if ph and c[-1] > ph and min(c[-4:-1]) <= ph:       # acabou de furar a resistência
        out.append("breakout_resistance")
    recent = bars[-3:]   # o toque pode ter sido hoje ou nos 2 pregões anteriores
    if min(b["l"] for b in recent) <= t["sma20"] * 1.015 and c[-1] > t["sma20"] and c[-1] > last["o"]:
        out.append("pullback_ma20")
    sup = lv["support"]
    if sup and min(b["l"] for b in recent) <= sup + 0.5 * a and c[-1] > last["o"] and c[-1] > sup:
        out.append("support_bounce")
    return out


def plan_for(price: float, a: float, lv: dict) -> dict | None:
    sup = lv["support"]
    if sup:
        stop, stop_basis = sup - STOP_BUFFER_ATR * a, "pivô de baixa"
    else:
        stop, stop_basis = price - 2 * a, "2 ATR (sem pivô)"
    risk = price - stop
    if risk < MIN_RISK_ATR * a:
        stop, stop_basis = price - MIN_RISK_ATR * a, "mínimo de 1 ATR"
        risk = price - stop
    if risk > MAX_RISK_ATR * a or risk <= 0 or risk >= price:
        return None  # pivô de baixa muito longe: risco alto demais para o ganho
    target, target_basis = price + FALLBACK_R * risk, "projeção de %dR" % FALLBACK_R
    for r in lv["resistances"]:
        if (r - price) / risk >= MIN_TARGET_R:
            target, target_basis = r, "próxima resistência"
            break
    rr = (target - price) / risk
    return {"entry": round(price, 2), "stop": round(stop, 2), "target": round(target, 2), "risk": round(risk, 2),
            "risk_pct": round(100 * risk / price, 2), "target_pct": round(100 * (target - price) / price, 2),
            "target_r": round(rr, 2), "stop_basis": stop_basis, "target_basis": target_basis,
            "support": sup and round(sup, 2), "resistance": lv["resistances"][0] if lv["resistances"] else None,
            "horizon_days": HORIZON}


def simulate(bars: list[dict], entry: float, stop: float, target: float, replays: int = REPLAYS, seed: int = 19) -> dict:
    """Caminhos de até HORIZON pregões a partir da entrada, sorteando dias do último ano do ativo.
    Dia que abre abaixo do stop (gap) conta como stop; stop é checado antes do alvo no mesmo dia."""
    pool = [(b["o"] / p["c"], b["h"] / p["c"], b["l"] / p["c"], b["c"] / p["c"]) for p, b in zip(bars[-251:], bars[-250:])]
    risk, rr = entry - stop, (target - entry) / (entry - stop)
    rng = random.Random(seed)
    cnt = {"target": 0, "stop": 0, "time": 0}
    sum_r = 0.0
    for _ in range(replays):
        p, outcome = entry, "time"
        for _day in range(HORIZON):
            o, h, l, c = rng.choice(pool)
            if p * o <= stop or p * l <= stop:
                outcome = "stop"; break
            if p * h >= target:
                outcome = "target"; break
            p *= c
        cnt[outcome] += 1
        sum_r += rr if outcome == "target" else -1.0 if outcome == "stop" else (p - entry) / risk
    return {"p_target": round(cnt["target"] / replays, 4), "p_stop": round(cnt["stop"] / replays, 4),
            "p_time": round(cnt["time"] / replays, 4), "avg_r": round(sum_r / replays, 3),
            "breakeven": round(1 / (1 + rr), 4), "replays": replays, "horizon_days": HORIZON}


MIN_AVG_R = 0.1


def recommendation(a: dict) -> dict:
    """Recomendada = tendência de alta + gatilho de compra + plano válido + chance acima do equilíbrio e retorno esperado positivo."""
    o = a["odds"]
    if not a["trend"]["up"]:
        why = "Sem tendência de alta: o método só compra a favor da tendência."
    elif not a["setups"]:
        why = "Sem gatilho de compra agora: aguarde pullback, repique no suporte ou rompimento."
    elif not a["plan"]:
        why = "Sem plano: o último pivô de baixa está longe demais (risco alto)."
    elif not a["liquid"]:
        why = "Liquidez baixa para operar."
    elif o and o["p_target"] < o["breakeven"]:
        why = "Chance de chegar ao alvo (%d%%) abaixo do equilíbrio (%d%%): a conta não compensa." % (round(o["p_target"] * 100), round(o["breakeven"] * 100))
    elif o and o["avg_r"] < MIN_AVG_R:
        why = "Retorno esperado baixo (%+.2fR)." % o["avg_r"]
    else:
        return {"ok": True, "label": "Recomendada para comprar",
                "reason": "Tendência de alta, gatilho de compra e chance acima do equilíbrio (%d%% contra %d%%)." % (round(o["p_target"] * 100), round(o["breakeven"] * 100))}
    return {"ok": False, "label": "Não recomendada", "reason": why}


def analyze(symbol: str, bars: list[dict], replays: int = REPLAYS, scan: bool = False) -> dict | None:
    """Análise de um ativo. scan=True (varredura) pula a simulação dos ativos sem tendência, sem plano ou ilíquidos."""
    if len(bars) < MIN_BARS:
        return None
    c = [b["c"] for b in bars]
    price, a = c[-1], atr(bars)
    t = trend(c)
    lv = levels(bars, price)
    tags = setups(bars, t, lv, a)
    turnover = sum(b["c"] * b.get("v", 0) for b in bars[-20:]) / 20
    plan = plan_for(price, a, lv)
    out = {"symbol": symbol, "price": round(price, 2), "setups": tags, "trend": t, "rsi": round(rsi(c) or 0, 1),
           "atr": round(a, 2), "turnover": round(turnover), "plan": plan, "odds": None, "last_bar": bars[-1]["t"],
           "dist_sma20_pct": round(100 * (price / t["sma20"] - 1), 2),
           "liquid": turnover >= MIN_TURNOVER,
           "support": lv["support"] and round(lv["support"], 2),
           "resistance": lv["resistances"][0] if lv["resistances"] else None}
    if plan and (not scan or (t["up"] and out["liquid"])):
        out["odds"] = simulate(bars, plan["entry"], plan["stop"], plan["target"], replays)
    out["recommend"] = recommendation(out)
    return out
