import time

from app.engine import EngineError
from app.tasks import TaskManager
from tests.conftest import AUTH


def wait(tm, tid, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        t = tm.get(tid)
        if t["status"] in ("done", "error"):
            return t
        time.sleep(0.01)
    raise AssertionError("tarefa não terminou")


def test_task_runs_and_returns_result():
    tm = TaskManager()
    t = wait(tm, tm.submit(lambda: {"x": 1}))
    assert t["status"] == "done" and t["result"] == {"x": 1}


def test_task_failure_is_captured_as_error():
    tm = TaskManager()

    def boom():
        raise EngineError("yahoo fora")

    t = wait(tm, tm.submit(boom))
    assert t["status"] == "error" and "yahoo fora" in t["error"]


def test_unknown_task_is_404(client):
    assert client.get("/tasks/nope", headers=AUTH).status_code == 404


def test_task_endpoint_returns_state(client):
    tid = client.app.state.tasks.submit(lambda: {"ok": 1})
    for _ in range(100):
        r = client.get("/tasks/" + tid, headers=AUTH).json()
        if r["status"] == "done":
            break
        time.sleep(0.01)
    assert r["result"] == {"ok": 1}
