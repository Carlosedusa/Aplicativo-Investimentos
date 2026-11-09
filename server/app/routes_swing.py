import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .paper.broker import PaperError
from .paper.prices import PriceError
from .swing import model, rules
from .swing.market import entry_window
from .swing.universe import IBOV

SYMBOL = r"^[A-Za-z]{4}\d{1,2}$"


class OrderBody(BaseModel):
    client_order_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    symbol: str = Field(pattern=SYMBOL)
    max_loss: float = Field(gt=0, le=1_000_000)
    train: bool = False
    confirm: bool = False


def build_router(require_token) -> APIRouter:
    r = APIRouter(dependencies=[Depends(require_token)])

    @r.get("/swing/market")
    def market(request: Request):
        now = request.app.state.clock()
        reasons = entry_window(now)
        return {"open": not reasons, "reasons": reasons, "universe": len(IBOV), "horizon_days": model.HORIZON}

    @r.post("/swing/scan")
    def scan(request: Request):
        source = request.app.state.swing_source

        def one(sym):
            for attempt in (0, 1):  # uma nova tentativa: o Yahoo às vezes recusa pedidos em sequência
                try:
                    return sym, model.analyze(sym, source(sym), scan=True), None
                except Exception as e:  # um ticker que falha não derruba a varredura
                    err = str(e)
                    if attempt == 0:
                        time.sleep(1.0)
            return sym, None, err

        def job():
            with ThreadPoolExecutor(max_workers=6) as pool:
                rows = list(pool.map(one, IBOV))
            ok = [a for _, a, e in rows if a]
            up = [a for a in ok if a["trend"]["up"] and a["liquid"]]
            hits = [a for a in up if a["setups"] and a["odds"]]
            hits.sort(key=lambda h: (-h["odds"]["avg_r"], h["symbol"]))
            watch = [a for a in up if not a["setups"] and a["odds"]]
            watch.sort(key=lambda a: abs(a["dist_sma20_pct"]))   # mais perto da média de 20 = pullback mais próximo
            best = next((h["symbol"] for h in hits if h["recommend"]["ok"]), None)
            return {"best": best, "scanned": len(ok), "failed": len(rows) - len(ok), "uptrend": len(up),
                    "with_setup": sum(1 for a in up if a["setups"]), "with_plan": sum(1 for a in up if a["plan"]),
                    "hits": hits[:50], "watch": watch[:15], "as_of": datetime.now(timezone.utc).isoformat(),
                    "note": "Lista para estudar, não para comprar. Chance = simulação com o último ano do próprio ativo."}

        return {"task_id": request.app.state.tasks.submit(job)}

    def analysis(request: Request, symbol: str) -> dict:
        if not re.match(SYMBOL, symbol):
            raise HTTPException(422, "Ticker inválido (ex.: PETR4).")
        sym = symbol.upper()
        try:
            a = model.analyze(sym, request.app.state.swing_source(sym))
        except PriceError as e:
            raise HTTPException(502, str(e))
        if a is None:
            raise HTTPException(404, "Poucos dados de %s para analisar." % sym)
        return a

    @r.get("/swing/asset/{symbol}")
    def asset(symbol: str, request: Request):
        return analysis(request, symbol)

    def equity_of(request: Request) -> float:
        b, feed = request.app.state.broker, request.app.state.feed
        total = b.cash()
        for p in b.positions():
            try:
                total += p.qty * float(feed.last(p.symbol))
            except Exception:
                total += p.qty * p.entry
        return total

    def verdict(request: Request, body: OrderBody) -> dict:
        a = analysis(request, body.symbol)
        b = request.app.state.broker
        return rules.evaluate(a["symbol"], a["plan"], body.max_loss, b.cash(), equity_of(request),
                              [p.symbol for p in b.positions() if p.horizon_days is not None],
                              request.app.state.clock(), body.train)

    @r.post("/swing/order/preview")
    def preview(body: OrderBody, request: Request):
        with request.app.state.trade_lock:
            return verdict(request, body)

    @r.post("/swing/orders")
    def place(body: OrderBody, request: Request):
        if not body.confirm:
            raise HTTPException(422, "Confirme a ordem de teste (confirm: true).")
        broker = request.app.state.broker
        existing = broker.find(body.client_order_id)
        if existing:
            return asdict(existing)
        with request.app.state.trade_lock:
            v = verdict(request, body)
            if v["verdict"] == "BLOCK":
                return JSONResponse({"detail": "Bloqueado pelo Risco: " + " ".join(v["reasons"]), "reasons": v["reasons"]},
                                    status_code=409)
            o = v["order"]
            try:
                pos = broker.place_bracket(body.client_order_id, o["symbol"], o["qty"], o["stop"], o["target"],
                                           horizon_days=o["horizon_days"])
            except PaperError as e:
                raise HTTPException(409, str(e))
        return asdict(pos)

    return r
