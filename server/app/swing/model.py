"""Swing trade em ações: sinais em barras diárias, plano por volatilidade (ATR) e chance de chegar ao alvo.

Chance = simulação (bootstrap) com as variações diárias do próprio ativo no último ano. Não é previsão."""
import random

HORIZON = 10          # pregões
STOP_ATR = 1.5        # stop a 1,5 ATR abaixo da entrada
TARGET_R = 2.0        # alvo = 2 x o risco
REPLAYS = 2000
MIN_BARS = 60
MIN_TURNOVER = 2_000_000.0   # R$ negociados por dia (média de 20 pregões)


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


def setups(c: list[float]) -> list[str]:
    last, hi20 = c[-1], max(c[-21:-1])
    ma20, ma20_prev = sum(c[-20:]) / 20, sum(c[-21:-1]) / 20
    out = []
    if last > hi20:
        out.append("breakout_20d")
    if c[-6] / c[-16] - 1 > 0.08 and (max(c[-5:]) - min(c[-5:])) / last < 0.05:
        out.append("bull_flag")
    if c[-2] < ma20_prev and last > ma20:
        out.append("reclaim_ma20")
    r_prev = rsi(c[:-1])
    if r_prev is not None and r_prev < 30 and last > c[-2]:
        out.append("oversold_bounce")
    return out


def plan_for(price: float, a: float) -> dict | None:
    risk = STOP_ATR * a
    if risk <= 0 or risk >= price:
        return None
    stop, target = price - risk, price + TARGET_R * risk
    return {"entry": round(price, 2), "stop": round(stop, 2), "target": round(target, 2), "risk": round(risk, 2),
            "risk_pct": round(100 * risk / price, 2), "target_pct": round(100 * TARGET_R * risk / price, 2),
            "target_r": TARGET_R, "horizon_days": HORIZON}


def simulate(bars: list[dict], entry: float, stop: float, target: float, replays: int = REPLAYS, seed: int = 19) -> dict:
    """Caminhos de até HORIZON pregões a partir da entrada, sorteando dias do último ano do ativo.
    Dia que abre abaixo do stop (gap) conta como stop; stop é checado antes do alvo no mesmo dia."""
    pool = [(b["o"] / p["c"], b["h"] / p["c"], b["l"] / p["c"], b["c"] / p["c"]) for p, b in zip(bars[-251:], bars[-250:])]
    risk = entry - stop
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
        sum_r += TARGET_R if outcome == "target" else -1.0 if outcome == "stop" else (p - entry) / risk
    return {"p_target": round(cnt["target"] / replays, 4), "p_stop": round(cnt["stop"] / replays, 4),
            "p_time": round(cnt["time"] / replays, 4), "avg_r": round(sum_r / replays, 3),
            "breakeven": round(1 / (1 + TARGET_R), 4), "replays": replays, "horizon_days": HORIZON}


def analyze(symbol: str, bars: list[dict], replays: int = REPLAYS, need_setup: bool = False) -> dict | None:
    """Análise de um ativo. need_setup=True devolve None se não houver nenhum sinal (uso da varredura)."""
    if len(bars) < MIN_BARS:
        return None
    c = [b["c"] for b in bars]
    tags = setups(c)
    if need_setup and not tags:
        return None
    turnover = sum(b["c"] * b.get("v", 0) for b in bars[-20:]) / 20
    if need_setup and turnover < MIN_TURNOVER:
        return None
    price, a = c[-1], atr(bars)
    plan = plan_for(price, a)
    out = {"symbol": symbol, "price": round(price, 2), "setups": tags, "rsi": round(rsi(c) or 0, 1),
           "atr": round(a, 2), "turnover": round(turnover), "plan": plan, "odds": None,
           "last_bar": bars[-1]["t"]}
    if plan:
        out["odds"] = simulate(bars, plan["entry"], plan["stop"], plan["target"], replays)
    return out
