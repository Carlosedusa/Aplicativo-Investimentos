import time

from tests.conftest import AUTH


def wait_task(client, tid):
    for _ in range(200):
        t = client.get("/tasks/" + tid, headers=AUTH).json()
        if t["status"] in ("done", "error"):
            return t
        time.sleep(0.01)
    raise AssertionError("tarefa não terminou")


def test_scan_orb_returns_task_and_result_is_watchlist(client, fake_engine):
    r = client.post("/scan/orb", json={"at": "10:15"}, headers=AUTH)
    assert r.status_code == 200
    t = wait_task(client, r.json()["task_id"])
    assert t["status"] == "done" and t["result"]["mode"] == "orb"
    assert fake_engine.calls[0] == ("scanner", ["orb", "--at", "10:15"])
    wl = client.get("/watchlist", headers=AUTH)
    assert wl.status_code == 200 and wl.json()["hits"]


def test_scan_rejects_unknown_mode_422(client, fake_engine):
    assert client.post("/scan/weekly", json={}, headers=AUTH).status_code == 422


def test_scan_rejects_option_injection_in_symbols(client, fake_engine):
    r = client.post("/scan/daily", json={"symbols": ["--offline"]}, headers=AUTH)
    assert r.status_code == 422


def test_watchlist_404_before_scan(client):
    assert client.get("/watchlist", headers=AUTH).status_code == 404


def test_news_passes_tickers_and_hours_to_tool(client, fake_engine):
    r = client.get("/news?tickers=TSLA,NVDA&hours=12", headers=AUTH)
    assert r.status_code == 200 and "moves" in r.json()
    assert fake_engine.calls[0] == ("news", ["--tickers", "TSLA", "NVDA", "--hours", "12"])


def test_entry_returns_status_field(client, fake_engine):
    r = client.get("/entry/TSLA", headers=AUTH)
    assert r.json()["status"] == "triggered"
    assert fake_engine.calls[0] == ("entry", ["check", "TSLA", "--write"])


def test_entry_rejects_bad_symbol(client, fake_engine):
    assert client.get("/entry/--x", headers=AUTH).status_code in (404, 422)


def test_exit_plan_writes_plan_file(client, fake_engine, settings):
    r = client.post("/exit/plan", json={"stop": "or-mid", "target": "2R"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["stop"] == 358.32
    assert fake_engine.calls[0] == ("exit", ["plan", "--write", "--stop", "or-mid", "--target", "2R"])
    assert (settings.workdir / "trader" / "plan.json").exists()


def test_timemachine_task_result_has_probabilities(client, fake_engine):
    r = client.post("/timemachine/run", json={"until": "15:55"}, headers=AUTH)
    t = wait_task(client, r.json()["task_id"])
    assert t["status"] == "done" and "p_target" in t["result"]["mc"]
    assert fake_engine.calls[0] == ("timemachine", ["run", "--write", "--until", "15:55"])


def test_engine_failure_becomes_502_with_message(client, fake_engine):
    fake_engine.fail["news"] = "Yahoo fora do ar"
    r = client.get("/news?tickers=TSLA", headers=AUTH)
    assert r.status_code == 502 and "Yahoo fora do ar" in r.json()["detail"]


def test_engine_failure_in_task_is_error_state(client, fake_engine):
    fake_engine.fail["scanner"] = "Yahoo fora do ar"
    r = client.post("/scan/orb", json={}, headers=AUTH)
    t = wait_task(client, r.json()["task_id"])
    assert t["status"] == "error" and "Yahoo" in t["error"]
