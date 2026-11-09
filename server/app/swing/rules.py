"""Regras de risco do swing (ordem de teste, R$)."""
from datetime import datetime

from .market import entry_window

MAX_OPEN = 5
MAX_POSITION_PCT = 30.0   # de uma ação, % do patrimônio
CASH_BUFFER_PCT = 10.0


def evaluate(symbol: str, plan: dict | None, max_loss: float, cash: float, equity: float,
             open_symbols: list[str], now: datetime, train: bool) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []
    window = entry_window(now)
    if window and not train:
        reasons += window
    elif window:
        warnings.append("Modo treino: " + window[0])
    if symbol in open_symbols:
        reasons.append("Você já tem uma posição aberta em %s." % symbol)
    if len(open_symbols) >= MAX_OPEN:
        reasons.append("Limite de %d posições abertas atingido." % MAX_OPEN)
    order = None
    if plan is None:
        reasons.append("Sem plano: a volatilidade do ativo não permite calcular stop e alvo.")
    else:
        qty = int(max_loss // plan["risk"])
        if qty < 1:
            reasons.append("A perda no stop de 1 ação (R$ %.2f) passa da sua Perda máxima (R$ %.2f). Aumente a Perda máxima." % (plan["risk"], max_loss))
        else:
            by_cash = int(cash * (1 - CASH_BUFFER_PCT / 100) // plan["entry"])
            by_pos = int(equity * MAX_POSITION_PCT / 100 // plan["entry"])
            cap = min(by_cash, by_pos)
            if cap < 1:
                reasons.append("Sem caixa ou limite de posição: R$ %.2f livres, máximo de %.0f%% do patrimônio por ação." % (cash, MAX_POSITION_PCT))
            elif cap < qty:
                warnings.append("Quantidade reduzida de %d para %d ações pelo caixa/limite de posição." % (qty, cap))
                qty = cap
        if qty >= 1:
            order = {"symbol": symbol, "qty": qty, "entry": plan["entry"], "stop": plan["stop"], "target": plan["target"],
                     "max_loss": round(qty * plan["risk"], 2), "target_gain": round(qty * (plan["target"] - plan["entry"]), 2),
                     "cost": round(qty * plan["entry"], 2), "horizon_days": plan["horizon_days"]}
    return {"verdict": "BLOCK" if reasons else "PASS", "reasons": reasons, "warnings": warnings,
            "order": None if reasons else order}
