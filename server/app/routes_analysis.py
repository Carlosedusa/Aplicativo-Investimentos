import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

SYMBOL = r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$"
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
RULE = r"^[A-Za-z0-9.:\-]{1,20}$"


class ScanBody(BaseModel):
    symbols: list[str] | None = Field(default=None, max_length=500)
    at: str | None = Field(default=None, pattern=HHMM)
    limit: int | None = Field(default=None, ge=1, le=20000)


class ExitBody(BaseModel):
    stop: str | None = Field(default=None, pattern=RULE)
    target: str | None = Field(default=None, pattern=RULE)


class TimeMachineBody(BaseModel):
    until: str | None = Field(default=None, pattern=HHMM)
    seed: int | None = None


def _run(request: Request, tool: str, args: list[str]) -> dict:
    return request.app.state.runner(tool, args)


def build_router(require_token) -> APIRouter:
    r = APIRouter(dependencies=[Depends(require_token)])

    @r.post("/scan/{mode}")
    def scan(mode: Literal["daily", "orb"], body: ScanBody, request: Request):
        args = [mode]
        if body.symbols:
            for s in body.symbols:
                if not re.match(SYMBOL, s):
                    raise HTTPException(422, "Símbolo inválido: %s" % s)
            args += ["--symbols", ",".join(s.upper() for s in body.symbols)]
        if body.at:
            if mode != "orb":
                raise HTTPException(422, "'at' só vale para o modo orb.")
            args += ["--at", body.at]
        if body.limit:
            args += ["--limit", str(body.limit)]
        runner = request.app.state.runner
        universe = request.app.state.settings.workdir / "trader" / "universe.txt"
        needs_universe = not body.symbols and not universe.exists()

        def job():
            if needs_universe:  # a skill exige a lista de ações antes da 1ª varredura
                runner("scanner", ["universe"])
            return runner("scanner", args)

        return {"task_id": request.app.state.tasks.submit(job)}

    @r.get("/watchlist")
    def watchlist(request: Request):
        path = request.app.state.settings.workdir / "trader" / "watchlist.json"
        if not path.exists():
            raise HTTPException(404, "Ainda não há watchlist: rode o scanner primeiro.")
        return json.loads(path.read_text())

    @r.get("/news")
    def news(request: Request, tickers: str = Query(pattern=r"^[A-Za-z0-9.,\-]{1,200}$"),
             hours: float = Query(default=48, gt=0, le=720)):
        names = [t for t in tickers.upper().split(",") if t]
        if not names or not all(re.match(SYMBOL, t) for t in names):
            raise HTTPException(422, "Tickers inválidos.")
        hours_txt = str(int(hours)) if hours == int(hours) else str(hours)
        return _run(request, "news", ["--tickers", *names, "--hours", hours_txt])

    @r.get("/entry/{symbol}")
    def entry(symbol: str, request: Request):
        if not re.match(SYMBOL, symbol):
            raise HTTPException(422, "Símbolo inválido.")
        return _run(request, "entry", ["check", symbol.upper(), "--write"])

    @r.post("/exit/plan")
    def exit_plan(body: ExitBody, request: Request):
        args = ["plan", "--write"]
        if body.stop:
            args += ["--stop", body.stop]
        if body.target:
            args += ["--target", body.target]
        return _run(request, "exit", args)

    @r.post("/timemachine/run")
    def timemachine(body: TimeMachineBody, request: Request):
        args = ["run", "--write"]
        if body.until:
            args += ["--until", body.until]
        if body.seed is not None:
            args += ["--seed", str(body.seed)]
        runner = request.app.state.runner
        return {"task_id": request.app.state.tasks.submit(lambda: runner("timemachine", args))}

    return r
