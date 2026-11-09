"""Notícias e sentimento da Alpha Vantage (NEWS_SENTIMENT) para a ação em destaque.

A chave grátis dá 25 consultas por dia: guardamos 6 h por ação e paramos em 20 consultas/dia."""
import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import date

# Ações da B3 com recibo (ADR) nos EUA: a Alpha Vantage cobre mais notícias pelo ticker americano.
ADR = {"PETR4": "PBR", "PETR3": "PBR", "VALE3": "VALE", "ITUB4": "ITUB", "BBDC4": "BBD", "BBDC3": "BBD",
       "ABEV3": "ABEV", "SBSP3": "SBS", "CSAN3": "CSAN", "GGBR4": "GGB", "SUZB3": "SUZ", "ELET3": "EBR",
       "ELET6": "EBR", "CMIG4": "CIG", "BRFS3": "BRFS", "CPFE3": "CPL", "UGPA3": "UGP", "NTCO3": "NTCO",
       "BPAC11": "BPAC", "ERJ": "ERJ", "EMBR3": "ERJ"}
URL = "https://www.alphavantage.co/query?"
DAILY_LIMIT = 20
TTL = 6 * 3600


class AlphaNews:
    def __init__(self, key: str, fetch=None):
        self.key, self._fetch = key, fetch or self._http
        self._lock, self._cache, self._day, self._used = threading.Lock(), {}, date.today(), 0

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _http(self, params: dict) -> dict:
        req = urllib.request.Request(URL + urllib.parse.urlencode(params), headers={"User-Agent": "daytrader-paper"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)

    def get(self, symbol: str) -> dict:
        if not self.available:
            return {"available": False}
        with self._lock:
            hit = self._cache.get(symbol)
            if hit and time.monotonic() - hit[0] < TTL:
                return hit[1]
            if date.today() != self._day:
                self._day, self._used = date.today(), 0
            if self._used >= DAILY_LIMIT:
                return {"available": True, "items": [], "error": "Limite diário de consultas da Alpha Vantage (grátis) atingido."}
            self._used += 1
        tick = ADR.get(symbol, symbol + ".SAO")
        try:
            doc = self._fetch({"function": "NEWS_SENTIMENT", "tickers": tick, "limit": "10", "sort": "LATEST",
                               "apikey": self.key})
        except Exception as e:
            return {"available": True, "items": [], "error": "Alpha Vantage indisponível agora (%s)." % e.__class__.__name__}
        out = parse(doc, tick)
        if "error" not in out:
            with self._lock:
                self._cache[symbol] = (time.monotonic(), out)
        return out


def label(score: float) -> str:
    return "positivo" if score >= 0.15 else "negativo" if score <= -0.15 else "neutro"


def parse(doc: dict, tick: str) -> dict:
    if not isinstance(doc, dict) or "feed" not in doc:
        msg = (doc or {}).get("Information") or (doc or {}).get("Note") or (doc or {}).get("Error Message") or ""
        return {"available": True, "items": [], "error": "Alpha Vantage não respondeu com notícias. " + str(msg)[:160]}
    items, scores = [], []
    for f in doc["feed"][:10]:
        own = next((t for t in f.get("ticker_sentiment", []) if t.get("ticker", "").upper() == tick.upper()), None)
        try:
            sc = float(own["ticker_sentiment_score"]) if own else float(f.get("overall_sentiment_score", 0))
        except (TypeError, ValueError):
            sc = 0.0
        scores.append(sc)
        t = str(f.get("time_published", ""))
        items.append({"title": f.get("title", ""), "source": f.get("source", ""), "url": f.get("url", ""),
                      "time": f"{t[6:8]}/{t[4:6]} {t[9:11]}:{t[11:13]}" if len(t) >= 13 else "",
                      "score": round(sc, 2), "label": label(sc)})
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0
    return {"available": True, "ticker": tick, "items": items, "avg_score": avg, "label": label(avg) if items else "sem notícias",
            "note": "Sentimento calculado pela Alpha Vantage; não é previsão."}
