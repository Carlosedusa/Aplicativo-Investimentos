import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-token"
AUTH = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def settings(tmp_path):
    return Settings(api_token=TOKEN, workdir=tmp_path / "work", starting_cash=5000.0)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c
