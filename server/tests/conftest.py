import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-token"
AUTH = {"Authorization": "Bearer " + TOKEN}


from tests.fakes import Clock, FakeFeed


@pytest.fixture
def settings(tmp_path):
    return Settings(api_token=TOKEN, workdir=tmp_path / "work", starting_cash=5000.0, monitor_interval=0)


@pytest.fixture
def feed():
    return FakeFeed(364.18)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def client(settings, feed, clock):
    with TestClient(create_app(settings, feed=feed, clock=clock)) as c:
        yield c


import json
from pathlib import Path

from app.engine import EngineError

SAMPLES = Path(__file__).parent / "samples"
SAMPLE_FOR = {"scanner": "scan_orb", "news": "news", "entry": "entry", "exit": "exit_plan",
              "timemachine": "timemachine", "budget": "budget", "risk": "risk"}


class FakeRunner:
    """Troca a skill real por amostras JSON; registra as chamadas."""

    def __init__(self, workdir):
        self.workdir = Path(workdir)
        self.calls = []
        self.fail = {}
        self.override = {}

    def __call__(self, tool, args):
        self.calls.append((tool, list(args)))
        if tool in self.fail:
            raise EngineError(self.fail[tool], 1, "")
        doc = self.override.get(tool) or json.loads((SAMPLES / (SAMPLE_FOR[tool] + ".json")).read_text())
        trader = self.workdir / "trader"
        trader.mkdir(parents=True, exist_ok=True)
        if tool == "scanner":
            (trader / "watchlist.json").write_text(json.dumps(doc))
        if tool == "budget":
            (trader / "orders.json").write_text(json.dumps(doc))
        if tool == "exit":
            (trader / "plan.json").write_text(json.dumps(doc))
        return doc


@pytest.fixture
def fake_engine(client, settings):
    fake = FakeRunner(settings.workdir)
    client.app.state.runner = fake
    return fake
