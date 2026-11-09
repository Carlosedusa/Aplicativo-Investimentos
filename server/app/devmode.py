"""Modo demonstração: troca a skill e o Yahoo por amostras fixas. Só para testes e protótipo."""
import json
from datetime import datetime
from pathlib import Path

from .engine import EngineError

SAMPLES = Path(__file__).resolve().parents[1] / "tests" / "samples"
SAMPLE_FOR = {"scanner": "scan_orb", "news": "news", "entry": "entry", "exit": "exit_plan",
              "timemachine": "timemachine", "budget": "budget", "risk": "risk"}


class FakeRunner:
    """Devolve amostras JSON no lugar da skill; registra as chamadas."""

    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.calls = []
        self.fail = {}
        self.override = {}

    def __call__(self, tool, args):
        self.calls.append((tool, list(args)))
        if tool in self.fail:
            raise EngineError(self.fail[tool], 1, "")
        doc = self.override.get(tool) or json.loads((SAMPLES / (SAMPLE_FOR[tool] + ".json")).read_text())
        trader = self.workdir / "trader"
        trader.mkdir(parents=True, exist_ok=True)
        if tool == "scanner" and args[:1] == ["universe"]:
            (trader / "universe.txt").write_text("TSLA\nAAPL\n")
            return {"symbols": 2}
        if tool == "scanner":
            (trader / "watchlist.json").write_text(json.dumps(doc))
        if tool == "budget":
            (trader / "orders.json").write_text(json.dumps(doc))
        if tool == "exit":
            (trader / "plan.json").write_text(json.dumps(doc))
        return doc


def demo_bars(symbol: str, n: int = 260) -> list[dict]:
    """Barras diárias de demonstração, estáveis por ticker (sem rede): tendência de alta e um pullback na média de 20."""
    import random
    from datetime import datetime, timedelta, timezone
    rng = random.Random(sum(map(ord, symbol)))
    p = 10 + rng.random() * 40
    day = datetime(2026, 11, 6, 13, 0, tzinfo=timezone.utc) - timedelta(days=n * 7 // 5 + 2)
    out = []
    while len(out) < n - 1:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        o = p * (1 + rng.gauss(0, 0.004)); c = o * (1 + rng.gauss(0.004, 0.012))
        out.append({"t": int(day.timestamp()), "o": o, "h": max(o, c) * (1 + abs(rng.gauss(0, 0.006))),
                    "l": min(o, c) * (1 - abs(rng.gauss(0, 0.006))), "c": c, "v": 5_000_000})
        p = c
    s20 = sum(b["c"] for b in out[-19:] + [{"c": p}]) / 20
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    c = s20 * 1.012
    out.append({"t": int(day.timestamp()), "o": s20, "h": c * 1.003, "l": s20 * 0.996, "c": c, "v": 5_000_000})
    return out


def demo_swing_source(symbol: str) -> list[dict]:
    return demo_bars(symbol)


class DemoFeed:
    """Preço fixo (TSLA 364,18), sem rede."""

    def __init__(self, prices=None):
        self.prices = prices or {"TSLA": 364.18}

    def last(self, symbol: str) -> float:
        import re
        if symbol not in self.prices and re.match(r"^[A-Z]{4}\d{1,2}$", symbol):
            return round(demo_bars(symbol)[-1]["c"], 2)
        return self.prices.get(symbol, 50.0)

    def candles(self, symbol: str, interval: str = "5m", limit: int = 120):
        if interval == "1d":
            return [{"t": b["t"], "o": round(b["o"], 2), "h": round(b["h"], 2), "l": round(b["l"], 2), "c": round(b["c"], 2)}
                    for b in demo_bars(symbol)[-limit:]]
        p, out = self.last(symbol), []
        for i in range(limit):
            base = p * (1 + 0.004 * ((i * 7) % 11 - 5) / 5)
            out.append({"t": 1_700_000_000 + 300 * i, "o": round(base, 2), "h": round(base * 1.004, 2),
                        "l": round(base * 0.996, 2), "c": round(base * (1.002 if i % 2 else 0.998), 2)})
        return out

    def range(self, symbol: str, since: datetime):
        p = self.last(symbol)
        return p, p


def demo_odds(symbol, entry, stop, target, k):
    """Chance de demonstração, estável por símbolo (sem rede)."""
    p = 0.2 + (sum(map(ord, symbol)) % 30) / 100
    return {"p_target": round(p, 4), "p_stop": round(0.9 - p, 4), "p_neither": 0.1, "sessions": 59}
