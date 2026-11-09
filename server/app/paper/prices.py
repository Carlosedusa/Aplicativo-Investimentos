import json
import re
import urllib.parse
import threading
import time
import urllib.request
from datetime import datetime
from typing import Protocol

UA = "Mozilla/5.0 (daytrader-paper)"
B3 = re.compile(r"^[A-Z]{4}\d{1,2}$")  # PETR4, VALE3, BPAC11...


def yahoo_symbol(symbol: str) -> str:
    """Ações da B3 usam o sufixo .SA no Yahoo."""
    s = symbol.upper()
    return urllib.parse.quote(s + ".SA" if B3.match(s) else s, safe="")


class PriceError(Exception):
    """Cotação indisponível (Yahoo fora do ar, símbolo desconhecido, resposta inesperada)."""


class PriceFeed(Protocol):
    def last(self, symbol: str) -> float: ...

    def range(self, symbol: str, since: datetime) -> tuple[float, float]:
        """(menor mínima, maior máxima) desde `since`, para checar stop e alvo."""


class YahooPriceFeed:
    """Cotações e velas do Yahoo (gratuito, não oficial). Ações da B3 entram pelo sufixo .SA."""

    URL = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=%s"
    CANDLE_RANGE = {"5m": "5d&interval=5m", "1d": "1y&interval=1d"}
    _cache: dict = {}
    _lock = threading.Lock()

    def _get(self, symbol: str, rng: str) -> dict:
        req = urllib.request.Request(self.URL % (yahoo_symbol(symbol), rng),
                                     headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)["chart"]["result"][0]

    def _bars(self, symbol: str, rng: str = "7d&interval=1m") -> dict:
        try:
            res = self._get(symbol, rng)
            q = res["indicators"]["quote"][0]
            return {"ts": res.get("timestamp") or [], "high": q["high"], "low": q["low"],
                    "close": q["close"], "price": res["meta"]["regularMarketPrice"]}
        except Exception as e:
            raise PriceError("Sem cotação de %s agora (Yahoo indisponível ou símbolo desconhecido)." % symbol) from e

    def last(self, symbol: str) -> float:
        return float(self._bars(symbol)["price"])

    def candles(self, symbol: str, interval: str = "5m", limit: int = 400) -> list[dict]:
        """Velas ('5m' ou '1d'), da mais antiga para a mais nova. Guarda 1 s por símbolo/intervalo."""
        if interval not in self.CANDLE_RANGE:
            raise PriceError("Intervalo inválido.")
        key = (symbol, interval)
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < 1.0:
                return hit[1][-limit:]
            try:
                res = self._get(symbol, self.CANDLE_RANGE[interval])
                q = res["indicators"]["quote"][0]
                rows = [{"t": t, "o": o, "h": h, "l": l, "c": c} for t, o, h, l, c in
                        zip(res.get("timestamp") or [], q["open"], q["high"], q["low"], q["close"])
                        if None not in (o, h, l, c)]
            except Exception as e:
                raise PriceError("Sem gráfico de %s agora (Yahoo indisponível ou símbolo desconhecido)." % symbol) from e
            rows = [{k: (v if k == "t" else round(float(v), 2)) for k, v in r.items()} for r in rows]
            self._cache[key] = (time.monotonic(), rows)
            return rows[-limit:]

    def range(self, symbol: str, since: datetime) -> tuple[float, float]:
        """(menor mínima, maior máxima) desde `since`; cobre dias parados (swing) com barras de 5 min."""
        old = (datetime.now(since.tzinfo) - since).days >= 6
        b = self._bars(symbol, "1mo&interval=5m" if old else "7d&interval=1m")
        since_ts = since.timestamp()
        lows = [l for t, l in zip(b["ts"], b["low"]) if t >= since_ts - 60 and l is not None]
        highs = [h for t, h in zip(b["ts"], b["high"]) if t >= since_ts - 60 and h is not None]
        price = float(b["price"])
        return (min(lows + [price]), max(highs + [price]))
