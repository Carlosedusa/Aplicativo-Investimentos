from app.swing.news import AlphaNews, parse
from tests.conftest import AUTH

DOC = {"feed": [
    {"title": "Petrobras sobe", "source": "X", "url": "http://a", "time_published": "20261109T123000",
     "overall_sentiment_score": 0.5, "ticker_sentiment": [{"ticker": "PBR", "ticker_sentiment_score": "0.30"}]},
    {"title": "Queda do petróleo", "source": "Y", "url": "http://b", "time_published": "20261108T090000",
     "overall_sentiment_score": -0.4, "ticker_sentiment": []}]}


def test_parse_uses_ticker_sentiment_and_labels():
    r = parse(DOC, "PBR")
    assert r["items"][0]["score"] == 0.3 and r["items"][1]["score"] == -0.4
    assert r["items"][0]["time"] == "09/11 12:30" and r["avg_score"] == -0.05 and r["label"] == "neutro"


def test_parse_reports_rate_limit_message():
    assert "limit" in parse({"Information": "rate limit reached"}, "PBR")["error"]


def test_news_caches_and_maps_adr():
    calls = []
    n = AlphaNews("k", fetch=lambda p: calls.append(p) or DOC)
    assert n.get("PETR4")["ticker"] == "PBR" and n.get("PETR4")["items"]
    assert len(calls) == 1 and calls[0]["tickers"] == "PBR"
    n.get("XYZW3"); assert calls[1]["tickers"] == "XYZW3.SAO"


def test_news_without_key_is_unavailable(client):
    assert client.get("/swing/news/PETR4", headers=AUTH).json() == {"available": False}


def test_news_stops_at_daily_limit():
    n = AlphaNews("k", fetch=lambda p: DOC)
    for i in range(25):
        n.get("AAAA%d" % i)
    assert "Limite diário" in n.get("ZZZZ3")["error"]
