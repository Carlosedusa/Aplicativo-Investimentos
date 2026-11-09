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
    assert "breakout_20d" in a["setups"]
    assert p["stop"] < p["entry"] < p["target"] and abs((p["target"] - p["entry"]) - 2 * p["risk"]) < 0.02
    o = a["odds"]
    assert 0 < o["p_target"] < 1 and abs(o["p_target"] + o["p_stop"] + o["p_time"] - 1) < 1e-6


def test_rules_block_and_size():
    plan = model.analyze("VALE3", demo_bars("VALE3"))["plan"]
    mon = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)   # segunda 11:00 em Brasília
    sat = datetime(2026, 11, 7, 14, 0, tzinfo=timezone.utc)
    ok = rules.evaluate("VALE3", plan, 100, 5000, 5000, [], mon, False)
    assert ok["verdict"] == "PASS" and ok["order"]["qty"] >= 1 and ok["order"]["max_loss"] <= 100
    blocked = rules.evaluate("VALE3", plan, 100, 5000, 5000, [], sat, False)
    assert blocked["verdict"] == "BLOCK" and "fechada" in blocked["reasons"][0]
    assert rules.evaluate("VALE3", plan, 100, 5000, 5000, [], sat, True)["verdict"] == "PASS"
    assert rules.evaluate("VALE3", plan, 0.01, 5000, 5000, [], mon, False)["verdict"] == "BLOCK"


def test_scan_ranks_by_expected_r(client):
    client.app.state.swing_source = demo_swing_source
    r = client.post("/swing/scan", headers=AUTH)
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
    assert r.status_code == 200 and r.json()["horizon_days"] == 10
    assert client.post("/swing/orders", json=body, headers=AUTH).json()["id"] == r.json()["id"]
    again = client.post("/swing/order/preview", json={**body, "client_order_id": "sw-2"}, headers=AUTH).json()
    assert again["verdict"] == "BLOCK"   # já tem posição em PETR4
