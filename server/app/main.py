import secrets
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .engine import EngineError, run_tool
from .odds import real_odds
from .routes_analysis import build_router as analysis_router
from .paper.broker import PaperBroker
from .paper.monitor import Monitor
from .paper.prices import PriceError, YahooPriceFeed
from .routes_paper import build_router as paper_router
from .routes_trade import build_router as trade_router
from .tasks import TaskManager


def create_app(settings: Settings | None = None, feed=None, clock=None) -> FastAPI:
    settings = settings or Settings.from_env()
    feed = feed or YahooPriceFeed()
    clock = clock or (lambda: datetime.now(timezone.utc))
    broker = PaperBroker(settings.workdir / "paper.db", feed, clock, settings.starting_cash)
    monitor = Monitor(broker, settings.monitor_interval)

    @asynccontextmanager
    async def lifespan(_app):
        monitor.start()
        yield
        monitor.stop()

    app = FastAPI(title="Day Trader API", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)  # contrato: docs/api/openapi.json
    app.state.trade_lock = threading.Lock()
    app.state.feed, app.state.clock = feed, clock
    app.state.broker, app.state.monitor = broker, monitor
    app.state.settings = settings
    app.state.tasks = TaskManager()
    app.state.odds = real_odds

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
                token.encode(), settings.api_token.encode()):
            raise HTTPException(401, "Token inválido.")

    app.state.require_token = require_token
    app.state.runner = lambda tool, args: run_tool(tool, args, settings.workdir)

    @app.exception_handler(EngineError)
    async def engine_error(_request, exc: EngineError):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(PriceError)
    async def price_error(_request, exc: PriceError):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    app.include_router(analysis_router(require_token))
    app.include_router(trade_router(require_token))
    app.include_router(paper_router(require_token))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/auth/check", dependencies=[Depends(require_token)])
    def auth_check():
        return {"ok": True}

    @app.get("/tasks/{task_id}", dependencies=[Depends(require_token)])
    def get_task(task_id: str):
        t = app.state.tasks.get(task_id)
        if t is None:
            raise HTTPException(404, "Tarefa não encontrada.")
        return t

    web_dir = Path(__file__).resolve().parents[2] / "web"
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
