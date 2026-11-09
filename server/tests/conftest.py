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


from app.devmode import FakeRunner


@pytest.fixture
def fake_engine(client, settings):
    fake = FakeRunner(settings.workdir)
    client.app.state.runner = fake
    return fake
