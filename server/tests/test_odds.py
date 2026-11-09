import datetime as dt
import json
import random

from app import odds


def _fake_chart():
    rng, ts, o, h, l, c = random.Random(1), [], [], [], [], []
    d, p, n = dt.datetime(2026, 9, 1, 13, 30, tzinfo=dt.timezone.utc), 100.0, 0
    while n < 30:
        if d.weekday() < 5:
            for i in range(78):
                cl = p * (1 + rng.gauss(0, 0.002))
                ts.append(int((d + dt.timedelta(minutes=5 * i)).timestamp()))
                o.append(p); h.append(max(p, cl) * 1.001); l.append(min(p, cl) * 0.999); c.append(cl); p = cl
            n += 1
        d += dt.timedelta(days=1)
    q = {"open": o, "high": h, "low": l, "close": c, "volume": [1] * len(ts)}
    meta = {"symbol": "TST", "dataGranularity": "5m", "regularMarketTime": int(d.timestamp())}
    return json.dumps({"chart": {"result": [{"meta": meta, "timestamp": ts, "indicators": {"quote": [q]}}]}})


def test_real_odds_computes_with_fetched_chart(monkeypatch):
    tm = odds._engine()
    monkeypatch.setattr(tm, "fetch_chart", lambda s: _fake_chart())
    odds._charts.clear()
    r = odds.compute_many(odds.real_odds, [{"symbol": "TST", "price": 100, "or_high": 99.9, "or_low": 99.0, "bar_index": 3}])
    o = r["odds"]["TST"]
    assert "error" not in o and 0 < o["p_target"] < 1 and o["basis"] == "faixa inicial"


def test_engine_loads_once_under_concurrency():
    from concurrent.futures import ThreadPoolExecutor
    odds._tm = None
    with ThreadPoolExecutor(8) as pool:
        mods = list(pool.map(lambda _: odds._engine(), range(16)))
    assert all(hasattr(m, "fetch_chart") and m is mods[0] for m in mods)
