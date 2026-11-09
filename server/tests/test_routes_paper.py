from tests.conftest import AUTH

ORDER = {"client_order_id": "ui-1", "symbol": "TSLA", "qty": 8, "stop": 358.32, "target": 375.9,
         "confirm": True}


def test_order_without_confirm_is_422(client, fake_engine):
    r = client.post("/paper/orders", json={**ORDER, "confirm": False}, headers=AUTH)
    assert r.status_code == 422
    assert client.get("/paper/positions", headers=AUTH).json() == []


def test_order_blocked_by_risk_is_409_even_with_confirm(client, fake_engine):
    fake_engine.override["risk"] = {
        "pass": 0, "block": 1, "warnings": [],
        "results": [{"verdict": "BLOCK", "reasons": ["max loss over the limit"], "warnings": []}]}
    r = client.post("/paper/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 409 and r.json()["reasons"] == ["max loss over the limit"]
    assert client.get("/paper/positions", headers=AUTH).json() == []


def test_order_passes_risk_and_opens_position(client, fake_engine):
    r = client.post("/paper/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 200 and r.json()["qty"] == 8 and r.json()["entry"] == 364.18
    tools = [c[0] for c in fake_engine.calls]
    assert tools == ["risk"]


def test_double_post_same_client_order_id_returns_one_position(client, fake_engine):
    a = client.post("/paper/orders", json=ORDER, headers=AUTH).json()
    b = client.post("/paper/orders", json=ORDER, headers=AUTH).json()
    assert a["id"] == b["id"]
    assert len(client.get("/paper/positions", headers=AUTH).json()) == 1


def test_order_with_too_little_cash_is_409(client, fake_engine):
    r = client.post("/paper/orders", json={**ORDER, "qty": 50}, headers=AUTH)
    assert r.status_code == 409 and "caixa" in r.json()["detail"].lower()


def test_positions_show_last_price_and_open_pnl(client, fake_engine, feed):
    client.post("/paper/orders", json=ORDER, headers=AUTH)
    feed.prices["TSLA"] = 366.18
    p = client.get("/paper/positions", headers=AUTH).json()[0]
    assert p["last"] == 366.18 and p["open_pnl"] == 16.0


def test_account_equity_uses_last_price(client, fake_engine, feed):
    client.post("/paper/orders", json=ORDER, headers=AUTH)
    feed.prices["TSLA"] = 366.18
    a = client.get("/paper/account", headers=AUTH).json()
    assert a["cash"] == round(5000 - 8 * 364.18, 2)
    assert a["equity"] == round(5000 + 16.0, 2) and a["open_pnl"] == 16.0 and a["closed_pnl"] == 0


def test_monitor_tick_closes_position_and_history_shows_it(client, fake_engine, feed, clock):
    client.post("/paper/orders", json=ORDER, headers=AUTH)
    clock.at(11, 0)
    feed.highs["TSLA"] = 376.0
    closed = client.app.state.monitor.run_once()
    assert closed[0].reason == "target"
    h = client.get("/paper/history", headers=AUTH).json()
    assert h[0]["reason"] == "target" and h[0]["pnl"] > 0
    assert client.get("/paper/account", headers=AUTH).json()["closed_pnl"] == h[0]["pnl"]


def test_paper_routes_require_token(client):
    assert client.get("/paper/positions").status_code == 401


def test_price_feed_down_on_order_is_502_with_message(client, fake_engine, feed):
    feed.bad.add("TSLA")
    r = client.post("/paper/orders", json=ORDER, headers=AUTH)
    assert r.status_code == 502 and "cotação" in r.json()["detail"].lower()


def test_concurrent_orders_never_overlap_risk_check(client, fake_engine):
    import threading, time
    state = {"now": 0, "max": 0}
    lock = threading.Lock()
    inner = client.app.state.runner

    def slow(tool, args):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05)
        try:
            return inner(tool, args)
        finally:
            with lock:
                state["now"] -= 1

    client.app.state.runner = slow
    threads = [threading.Thread(target=lambda i=i: client.post(
        "/paper/orders", json={**ORDER, "client_order_id": "c%d" % i, "qty": 1}, headers=AUTH)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert state["max"] == 1


def test_docs_and_openapi_require_no_public_access(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
