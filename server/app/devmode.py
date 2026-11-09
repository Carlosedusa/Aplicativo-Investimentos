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


class DemoFeed:
    """Preço fixo (TSLA 364,18), sem rede."""

    def __init__(self, prices=None):
        self.prices = prices or {"TSLA": 364.18}

    def last(self, symbol: str) -> float:
        return self.prices.get(symbol, 50.0)

    def range(self, symbol: str, since: datetime):
        p = self.last(symbol)
        return p, p
