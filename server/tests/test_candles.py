from tests.conftest import AUTH


def test_candles_returns_15m_bars(client):
    r = client.get("/candles/TSLA", headers=AUTH)
    assert r.status_code == 200
    d = r.json()
    assert d["interval"] == "15m" and d["candles"][0].keys() >= {"t", "o", "h", "l", "c"}


def test_candles_rejects_bad_symbol(client):
    assert client.get("/candles/%24%24", headers=AUTH).status_code in (404, 422)
