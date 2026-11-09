"""Ponto de entrada: `uvicorn app.asgi:app`. FAKE_ENGINE=1 liga o modo demonstração."""
import os

from .config import Settings
from .devmode import DemoFeed, FakeRunner, demo_odds, demo_swing_source
from .main import create_app

settings = Settings.from_env()
demo = os.environ.get("FAKE_ENGINE") == "1"
app = create_app(settings, feed=DemoFeed() if demo or os.environ.get("FAKE_PRICES") == "1" else None)
if demo:
    app.state.runner = FakeRunner(settings.workdir)
    app.state.odds = demo_odds
    app.state.swing_source = demo_swing_source
