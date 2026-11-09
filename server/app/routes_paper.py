import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .paper.broker import PaperError
from .routes_trade import run_risk, trader_dir


class OrderBody(BaseModel):
    client_order_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    symbol: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
    qty: int = Field(gt=0, le=1_000_000)
    stop: float = Field(gt=0)
    target: float = Field(gt=0)
    confirm: bool = False
    train: bool = False


def _last(feed, symbol):
    try:
        return float(feed.last(symbol))
    except Exception:
        return None


def build_router(require_token) -> APIRouter:
    r = APIRouter(dependencies=[Depends(require_token)])

    def write_risk_inputs(request: Request, body: OrderBody, price: float, now_iso: str) -> None:
        d = trader_dir(request)
        symbol = body.symbol.upper()
        per_share = round(price - body.stop, 2)
        order = {
            "symbol": symbol, "side": "buy", "qty": str(body.qty), "type": "market",
            "time_in_force": "day", "order_class": "bracket",
            "take_profit_limit_price": "%.2f" % body.target,
            "stop_loss_stop_price": "%.2f" % body.stop,
            "why": "ordem de teste confirmada pelo usuário",
            "plan": {"entry": price, "stop": body.stop, "target": body.target,
                     "risk_per_share": per_share, "max_loss": round(per_share * body.qty, 2),
                     "setup": "manual", "flat_by": "15:55"},
        }
        (d / "orders.json").write_text(json.dumps({"orders": [order]}, indent=2))
        (d / "prices.json").write_text(json.dumps(
            {"as_of": now_iso, "prices": {symbol: price}, "detail": {symbol: {"time": now_iso}}}))

    @r.post("/paper/orders")
    def place_order(body: OrderBody, request: Request):
        if not body.confirm:
            raise HTTPException(422, "Confirme a ordem de teste (confirm: true).")
        broker, feed = request.app.state.broker, request.app.state.feed
        existing = broker.find(body.client_order_id)
        if existing:  # reenvio do mesmo clique: devolve a mesma posição
            return asdict(existing)
        symbol = body.symbol.upper()
        price = float(feed.last(symbol))
        now_iso = request.app.state.clock().isoformat().replace("+00:00", "Z")
        # Um pedido por vez: os arquivos de entrada do Risco são compartilhados.
        with request.app.state.trade_lock:
            write_risk_inputs(request, body, price, now_iso)
            verdict = run_risk(request, body.train)
            if verdict["verdict"] == "BLOCK":
                return JSONResponse({"detail": "Bloqueado pelo Risco: " + "; ".join(verdict["reasons"]),
                                     "reasons": verdict["reasons"]}, status_code=409)
            try:
                pos = broker.place_bracket(body.client_order_id, symbol, body.qty, body.stop, body.target)
            except PaperError as e:
                raise HTTPException(409, str(e))
        return asdict(pos)

    @r.get("/paper/positions")
    def positions(request: Request):
        broker, feed = request.app.state.broker, request.app.state.feed
        out = []
        for p in broker.positions():
            last = _last(feed, p.symbol)
            row = asdict(p)
            row["last"] = last
            row["open_pnl"] = None if last is None else round((last - p.entry) * p.qty, 2)
            out.append(row)
        return out

    @r.get("/paper/history")
    def history(request: Request):
        return [asdict(t) for t in request.app.state.broker.history()]

    @r.get("/paper/account")
    def account(request: Request):
        broker, feed = request.app.state.broker, request.app.state.feed
        open_pnl, market = 0.0, 0.0
        for p in broker.positions():
            last = _last(feed, p.symbol) or p.entry
            open_pnl += (last - p.entry) * p.qty
            market += last * p.qty
        closed_pnl = round(sum(t.pnl for t in broker.history()), 2)
        cash = broker.cash()
        return {"starting_cash": broker.starting_cash, "cash": cash, "equity": round(cash + market, 2),
                "open_pnl": round(open_pnl, 2), "closed_pnl": closed_pnl}

    return r
