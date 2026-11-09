"""Barras diárias (1 ano) de ações da B3 no Yahoo, com cache de 5 minutos."""
import json
import threading
import time
import urllib.request

from ..paper.prices import UA, PriceError, yahoo_symbol


class YahooDailySource:
    def __init__(self, ttl: float = 300.0):
        self.ttl, self._lock, self._cache = ttl, threading.Lock(), {}

    def __call__(self, symbol: str) -> list[dict]:
        with self._lock:
            hit = self._cache.get(symbol)
            if hit and time.monotonic() - hit[0] < self.ttl:
                return hit[1]
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=1y&interval=1d" % yahoo_symbol(symbol)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                res = json.load(resp)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            bars = [{"t": int(t), "o": o, "h": h, "l": l, "c": c, "v": v or 0} for t, o, h, l, c, v in
                    zip(res.get("timestamp") or [], q["open"], q["high"], q["low"], q["close"], q["volume"])
                    if None not in (o, h, l, c)]
        except Exception as e:
            raise PriceError("Sem dados de %s agora (Yahoo indisponível ou ticker desconhecido)." % symbol) from e
        with self._lock:
            self._cache[symbol] = (time.monotonic(), bars)
        return bars
