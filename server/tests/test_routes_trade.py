import json

from tests.conftest import AUTH


def make_plan(client):
    assert client.post("/exit/plan", json={}, headers=AUTH).status_code == 200


def test_budget_requires_plan_409(client, fake_engine):
    r = client.post("/budget/size", json={"budget": 5000, "max_loss": 50}, headers=AUTH)
    assert r.status_code == 409 and "plano" in r.json()["detail"].lower()


def test_budget_returns_qty_and_bracket(client, fake_engine, settings):
    make_plan(client)
    r = client.post("/budget/size", json={"budget": 5000, "max_loss": 50}, headers=AUTH)
    assert r.status_code == 200
    b = r.json()
    assert (b["symbol"], b["qty"], b["entry"], b["stop"], b["target"]) == ("TSLA", 8, 364.18, 358.32, 375.9)
    assert b["max_loss"] == 46.88
    cfg = json.loads((settings.workdir / "trader" / "config.json").read_text())
    assert cfg["budget"] == 5000 and cfg["max_loss_per_trade_usd"] == 50
    assert fake_engine.calls[-1] == ("budget", ["--write"])


def test_budget_rejects_non_positive_values(client, fake_engine):
    make_plan(client)
    assert client.post("/budget/size", json={"budget": 0, "max_loss": 50}, headers=AUTH).status_code == 422


def test_risk_requires_orders_409(client, fake_engine):
    assert client.post("/risk/check", headers=AUTH).status_code == 409


def test_risk_pass(client, fake_engine):
    make_plan(client)
    client.post("/budget/size", json={"budget": 5000, "max_loss": 50}, headers=AUTH)
    r = client.post("/risk/check", headers=AUTH)
    assert r.status_code == 200 and r.json() == {"verdict": "PASS", "reasons": [], "warnings": []}


def test_risk_block_has_reasons(client, fake_engine):
    make_plan(client)
    client.post("/budget/size", json={"budget": 5000, "max_loss": 50}, headers=AUTH)
    fake_engine.override["risk"] = {
        "pass": 0, "block": 1, "warnings": [],
        "results": [{"verdict": "BLOCK", "reasons": ["max loss $65.28 over the $50 limit"], "warnings": []}],
    }
    r = client.post("/risk/check", headers=AUTH).json()
    assert r["verdict"] == "BLOCK" and r["reasons"] == ["max loss $65.28 over the $50 limit"]
