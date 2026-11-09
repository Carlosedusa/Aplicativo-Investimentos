"""Chance de o preço chegar ao alvo antes do stop, usando o motor da Máquina do Tempo (versão rápida)."""
import importlib.util
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .engine import ENGINE_DIR

TARGET_R = 2.0
DAILY_RISK = 0.01   # pré-mercado não tem faixa de abertura: stop padrão 1% abaixo
_tm = None


def _engine():
    global _tm
    if _tm is None:
        spec = importlib.util.spec_from_file_location("tm_engine", ENGINE_DIR / "trader-timemachine" / "timemachine.py")
        _tm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_tm)
    return _tm


_charts: dict = {}   # símbolo -> (hora, texto): os 60 dias não mudam em minutos


def _chart(tm, symbol):
    hit = _charts.get(symbol)
    if hit and time.monotonic() - hit[0] < 600:
        return hit[1]
    text = _chart(tm, symbol)
    _charts[symbol] = (time.monotonic(), text)
    return text


def real_odds(symbol: str, entry: float, stop: float, target: float, k: int, replays: int = 2000) -> dict:
    tm = _engine()
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # o motor usa UTC sem fuso
    text = _chart(tm, symbol)
    _, bars, _ = tm.parse_bars(tm.chart_result(text, symbol), now)
    today = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    sessions, _ = tm.full_sessions(tm.split_sessions(bars), today)
    if len(sessions) < tm.MIN_SESSIONS:
        raise tm.TMError("poucos pregões para simular %s" % symbol)
    mc = tm.simulate(tm.build_pool(sessions), entry, stop, target, k, tm.SESSION_BARS - 1, replays)
    return {"p_target": mc["p_target"], "p_stop": mc["p_stop"], "p_neither": mc["p_neither"], "sessions": len(sessions)}


def plan_for(hit: dict) -> tuple[float, float, float, int, str]:
    """(entrada, stop, alvo, vela de entrada, base). Rompimento: stop no meio da faixa inicial, alvo 2R."""
    price = float(hit["price"])
    if hit.get("or_high") is not None and hit.get("or_low") is not None:
        stop, k, basis = (float(hit["or_high"]) + float(hit["or_low"])) / 2, int(hit.get("bar_index", 3)), "faixa inicial"
    else:
        stop, k, basis = price * (1 - DAILY_RISK), 3, "stop padrão de 1%"
    if not 0 < stop < price:  # preço colado no stop: usa o padrão
        stop, basis = price * (1 - DAILY_RISK), "stop padrão de 1%"
    return price, stop, price + TARGET_R * (price - stop), k, basis


def compute_many(fn, hits: list[dict], workers: int = 3) -> dict:
    def one(hit):
        entry, stop, target, k, basis = plan_for(hit)
        try:
            r = fn(hit["symbol"], entry, stop, target, k)
        except Exception as e:  # um ativo que falha não derruba os outros
            return hit["symbol"], {"error": str(e)}
        return hit["symbol"], dict(r, stop=round(stop, 2), target=round(target, 2), basis=basis,
                                   breakeven=round(1 / (1 + TARGET_R), 4), target_r=TARGET_R)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {"odds": dict(pool.map(one, hits))}
