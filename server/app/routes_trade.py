import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field


class BudgetBody(BaseModel):
    budget: float = Field(gt=0, le=10_000_000)
    max_loss: float = Field(gt=0, le=1_000_000)


def trader_dir(request: Request):
    d = request.app.state.settings.workdir / "trader"
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_risk(doc: dict) -> dict:
    results = doc.get("results", [])
    blocked = doc.get("block", 0) > 0 or any(r.get("verdict") == "BLOCK" for r in results)
    reasons = [x for r in results for x in r.get("reasons", [])]
    warnings = list(doc.get("warnings", [])) + [x for r in results for x in r.get("warnings", [])]
    return {"verdict": "BLOCK" if blocked else "PASS", "reasons": reasons, "warnings": warnings}


def run_risk(request: Request, train: bool = False) -> dict:
    """Modo treino (só dinheiro de teste): ignora o horário do mercado; todas as outras regras continuam valendo."""
    args: list[str] = []
    if train:
        d = trader_dir(request)
        cfg_path = d / "config.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        cfg.update({"no_entries_before": None, "no_entries_after": None})
        (d / "config_treino.json").write_text(json.dumps(cfg, indent=2))
        args = ["--config", str(d / "config_treino.json")]
    return normalize_risk(request.app.state.runner("risk", args))


def build_router(require_token) -> APIRouter:
    r = APIRouter(dependencies=[Depends(require_token)])

    @r.post("/budget/size")
    def budget_size(body: BudgetBody, request: Request):
        d = trader_dir(request)
        if not (d / "plan.json").exists():
            raise HTTPException(409, "Sem plano de saída: gere o plano primeiro (/exit/plan).")
        cfg_path = d / "config.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        cfg.update({"budget": body.budget, "max_loss_per_trade_usd": body.max_loss})
        cfg_path.write_text(json.dumps(cfg, indent=2))
        with request.app.state.trade_lock:
            doc = request.app.state.runner("budget", ["--write"])
        if not doc.get("orders"):
            raise HTTPException(409, (doc.get("sizing") or {}).get("refusal") or "O Orçamento não gerou ordem.")
        order = doc["orders"][0]
        plan = order.get("plan", {})
        return {
            "symbol": order["symbol"], "side": order["side"], "qty": int(order["qty"]),
            "entry": plan.get("entry"), "stop": float(order["stop_loss_stop_price"]),
            "target": float(order["take_profit_limit_price"]),
            "risk_per_share": plan.get("risk_per_share"), "max_loss": plan.get("max_loss"),
            "why": order.get("why", ""), "order": order,
        }

    @r.post("/risk/check")
    def risk_check(request: Request, train: bool = False):
        if not (trader_dir(request) / "orders.json").exists():
            raise HTTPException(409, "Sem ordem para checar: calcule o tamanho da posição primeiro.")
        with request.app.state.trade_lock:
            return run_risk(request, train)

    @r.get("/market/status")
    def market_status(request: Request):
        """O mercado aceita entradas agora? (horário de Nova York, feriados da NYSE)"""
        import importlib.util
        from .engine import ENGINE_DIR
        spec = importlib.util.spec_from_file_location("risk_check", ENGINE_DIR / "trader-risk" / "check.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from zoneinfo import ZoneInfo
        now = request.app.state.clock().astimezone(ZoneInfo("America/New_York"))
        reasons, _ = mod.window_check(now, mod.DEFAULTS)
        return {"open": not reasons, "reasons": reasons, "now_new_york": now.strftime("%Y-%m-%d %H:%M")}

    return r
