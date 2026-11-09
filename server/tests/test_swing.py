import time
from datetime import datetime, timezone

from app.devmode import demo_bars, demo_swing_source
from app.paper.prices import yahoo_symbol
from app.swing import model, rules
from tests.conftest import AUTH


def _wait(client, tid):
    for _ in range(200):
        t = client.get("/tasks/" + tid, headers=AUTH).json()
        if t["status"] in ("done", "error"):
            return t
        time.sleep(0.05)


def test_b3_tickers_use_sa_suffix():
    assert yahoo_symbol("PETR4") == "PETR4.SA" and yahoo_symbol("BPAC11") == "BPAC11.SA" and yahoo_symbol("TSLA") == "TSLA"


def test_analysis_builds_atr_plan_and_odds():
    a = model.analyze("PETR4", demo_bars("PETR4"))
    p = a["plan"]
    assert a["trend"]["up"] and "pullback_ma20" in a["setups"]
    assert p["stop"] < p["entry"] < p["target"] and abs((p["target"] - p["entry"]) - p["target_r"] * p["risk"]) < 0.05
    assert p["stop_basis"] == "pivô de baixa" and p["horizon_days"] == 15
    o = a["odds"]
    assert 0 < o["p_target"] < 1 and abs(o["p_target"] + o["p_stop"] + o["p_time"] - 1) < 1e-6


def test_rules_block_and_size():
    plan = model.analyze("PETR4", demo_bars("PETR4"))["plan"]
    mon = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)   # segunda 11:00 em Brasília
    sat = datetime(2026, 11, 7, 14, 0, tzinfo=timezone.utc)
    ok = rules.evaluate("PETR4", plan, 100, 5000, 5000, [], mon, False)
    assert ok["verdict"] == "PASS" and ok["order"]["qty"] >= 1 and ok["order"]["max_loss"] <= 100
    blocked = rules.evaluate("PETR4", plan, 100, 5000, 5000, [], sat, False)
    assert blocked["verdict"] == "BLOCK" and "fechada" in blocked["reasons"][0]
    assert rules.evaluate("PETR4", plan, 100, 5000, 5000, [], sat, True)["verdict"] == "PASS"
    assert rules.evaluate("PETR4", plan, 0.01, 5000, 5000, [], mon, False)["verdict"] == "BLOCK"


def test_scan_ranks_by_expected_r(client):
    client.app.state.swing_source = demo_swing_source
    r = client.post("/swing/scan", json={}, headers=AUTH)
    t = _wait(client, r.json()["task_id"])
    assert t["status"] == "done"
    hits = t["result"]["hits"]
    assert hits and [h["odds"]["avg_r"] for h in hits] == sorted((h["odds"]["avg_r"] for h in hits), reverse=True)


def test_order_flow_holds_overnight(client):
    client.app.state.swing_source = demo_swing_source
    client.app.state.feed.prices["PETR4"] = round(demo_bars("PETR4")[-1]["c"], 2)
    body = {"client_order_id": "sw-1", "symbol": "PETR4", "max_loss": 100, "train": True, "confirm": True}
    pv = client.post("/swing/order/preview", json=body, headers=AUTH).json()
    assert pv["verdict"] == "PASS"
    r = client.post("/swing/orders", json=body, headers=AUTH)
    assert r.status_code == 200 and r.json()["horizon_days"] == 15
    assert client.post("/swing/orders", json=body, headers=AUTH).json()["id"] == r.json()["id"]
    again = client.post("/swing/order/preview", json={**body, "client_order_id": "sw-2"}, headers=AUTH).json()
    assert again["verdict"] == "BLOCK"   # já tem posição em PETR4


def _bars(closes, spread=0.5):
    return [{"t": i, "o": c, "h": c + spread, "l": c - spread, "c": c, "v": 1} for i, c in enumerate(closes)]


def test_pivots_need_three_candles_each_side():
    #            0   1   2   3   4   5   6   7   8   9  10  11  12
    closes = [10, 11, 12, 15, 12, 11, 10, 9, 8, 6, 8, 9, 10]
    highs, lows = model.pivots(_bars(closes))
    assert [i for i, _ in highs] == [3] and [i for i, _ in lows] == [9]
    assert model.pivots(_bars(closes[:11]))[1] == []   # o fundo ainda não tem 3 velas depois: não confirmado


def test_stop_goes_below_pivot_low_and_target_at_next_resistance():
    lv = {"support": 95.0, "resistances": [101.0, 112.0], "last_pivot_high": 112.0}
    p = model.plan_for(100.0, 2.0, lv)       # risco = 5 + 0,5 = 5,5 ; 101 dá só 0,18R, 112 dá 2,2R
    assert p["stop"] == 94.5 and p["target"] == 112.0 and p["target_basis"] == "próxima resistência"
    assert model.plan_for(100.0, 2.0, {"support": 80.0, "resistances": [], "last_pivot_high": None}) is None  # pivô longe demais
    p2 = model.plan_for(100.0, 2.0, {"support": 99.8, "resistances": [], "last_pivot_high": None})
    assert p2["stop"] == 98.0 and p2["target_basis"].startswith("projeção")   # stop mínimo de 1 ATR, alvo 3R


def test_no_setup_without_uptrend():
    down = _bars([100 - i * 0.3 for i in range(120)])
    a = model.analyze("PETR4", down)
    assert a["trend"]["up"] is False and a["setups"] == []


def test_scan_reports_funnel_and_watchlist(client):
    def source(sym):
        # alta firme e sem recuo: tendência de alta, mas sem pullback/rompimento recente => "acompanhar"
        return [{"t": 1_700_000_000 + 86400 * i, "o": 10 + i * 0.1, "h": 10.3 + i * 0.1, "l": 9.8 + i * 0.1,
                 "c": 10.1 + i * 0.1, "v": 5_000_000} for i in range(120)]
    client.app.state.swing_source = source
    t = _wait(client, client.post("/swing/scan", json={}, headers=AUTH).json()["task_id"])
    r = t["result"]
    assert t["status"] == "done" and r["scanned"] > 0 and r["uptrend"] == r["scanned"]
    assert r["hits"] == [] or all(h["setups"] for h in r["hits"])
    assert r["watch"] and all(not w["setups"] and w["odds"] for w in r["watch"])
    assert set(r) >= {"with_setup", "with_plan", "failed"}


def test_recommendation_requires_edge():
    a = model.analyze("PETR4", demo_bars("PETR4"))
    good = dict(a, odds=dict(a["odds"], p_target=0.5, breakeven=0.3, avg_r=0.5))
    bad = dict(a, odds=dict(a["odds"], p_target=0.1, breakeven=0.3, avg_r=-0.2))
    assert model.recommendation(good)["ok"] is True
    r = model.recommendation(bad)
    assert r["ok"] is False and "abaixo do equilíbrio" in r["reason"]
    assert model.recommendation(dict(a, setups=[]))["ok"] is False
    assert model.recommendation(dict(a, trend={"up": False}))["ok"] is False


def test_scan_all_b3_covers_more_tickers_and_reports_progress(client):
    from app.swing.universe import ALL_B3, IBOV
    assert len(ALL_B3) > 2 * len(IBOV) and len(set(ALL_B3)) == len(ALL_B3)
    client.app.state.swing_source = demo_swing_source
    t = _wait(client, client.post("/swing/scan", json={"universe": "all"}, headers=AUTH).json()["task_id"])
    assert t["status"] == "done" and t["result"]["total"] == len(ALL_B3) and t["result"]["scanned"] > len(IBOV)
    p = client.get("/swing/scan/progress", headers=AUTH).json()
    assert p["done"] == p["total"] == len(ALL_B3)
