import json
import urllib.request
from datetime import datetime
from typing import Protocol

UA = "Mozilla/5.0 (daytrader-paper)"


class PriceFeed(Protocol):
    def last(self, symbol: str) -> float: ...

    def range(self, symbol: str, since: datetime) -> tuple[float, float]:
        """(menor mínima, maior máxima) desde `since`, para checar stop e alvo."""


class YahooPriceFeed:
    """Barras de 1 minuto do Yahoo (gratuito, não oficial)."""

    def _bars(self, symbol: str) -> dict:
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1m" % symbol
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            doc = json.load(resp)
        res = doc["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        return {"ts": res.get("timestamp") or [], "high": q["high"], "low": q["low"],
                "close": q["close"], "price": res["meta"]["regularMarketPrice"]}

    def last(self, symbol: str) -> float:
        return float(self._bars(symbol)["price"])

    def range(self, symbol: str, since: datetime) -> tuple[float, float]:
        b = self._bars(symbol)
        since_ts = since.timestamp()
        lows = [l for t, l in zip(b["ts"], b["low"]) if t >= since_ts - 60 and l is not None]
        highs = [h for t, h in zip(b["ts"], b["high"]) if t >= since_ts - 60 and h is not None]
        price = float(b["price"])
        return (min(lows + [price]), max(highs + [price]))
