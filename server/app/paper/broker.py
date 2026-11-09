import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .prices import PriceFeed

NY = ZoneInfo("America/New_York")
FLAT_BY = time(15, 55)


class PaperError(Exception):
    pass


@dataclass
class Position:
    id: int
    symbol: str
    qty: int
    entry: float
    stop: float
    target: float
    opened_at: str


@dataclass
class ClosedTrade:
    id: int
    symbol: str
    qty: int
    entry: float
    stop: float
    target: float
    opened_at: str
    closed_at: str
    exit_price: float
    reason: str  # "stop" | "target" | "eod"
    pnl: float


SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_order_id TEXT UNIQUE NOT NULL,
  symbol TEXT NOT NULL, qty INTEGER NOT NULL,
  entry REAL NOT NULL, stop REAL NOT NULL, target REAL NOT NULL,
  opened_at TEXT NOT NULL, checked_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  exit_price REAL, reason TEXT, closed_at TEXT, pnl REAL
)"""
COLS = "id, symbol, qty, entry, stop, target, opened_at"


class PaperBroker:
    """Livro de ordens de teste: compra a mercado, vigia stop/alvo e fecha às 15:55 ET."""

    def __init__(self, db_path: Path, feed: PriceFeed, clock: Callable[[], datetime],
                 starting_cash: float):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.execute(SCHEMA)
        self._db.commit()
        self._lock = threading.RLock()
        self.feed, self.clock, self.starting_cash = feed, clock, starting_cash

    def _now(self) -> datetime:
        return self.clock().astimezone(timezone.utc)

    def cash(self) -> float:
        with self._lock:
            spent, back = self._db.execute(
                "SELECT COALESCE(SUM(qty*entry),0), COALESCE(SUM(CASE WHEN status='closed' "
                "THEN qty*exit_price END),0) FROM positions").fetchone()
        return round(self.starting_cash - spent + back, 2)

    def place_bracket(self, client_order_id: str, symbol: str, qty: int,
                      stop: float, target: float) -> Position:
        with self._lock:
            row = self._db.execute("SELECT %s FROM positions WHERE client_order_id=?" % COLS,
                                   (client_order_id,)).fetchone()
            if row:
                return Position(*row)
            if qty <= 0:
                raise PaperError("Quantidade deve ser maior que zero.")
            price = float(self.feed.last(symbol))
            if not stop < price < target:
                raise PaperError("Stop (%.2f) e alvo (%.2f) precisam ficar abaixo e acima do preço atual (%.2f)."
                                 % (stop, target, price))
            cost = qty * price
            if cost > self.cash():
                raise PaperError("Caixa virtual insuficiente: precisa de %.2f e há %.2f." % (cost, self.cash()))
            now = self._now().isoformat()
            cur = self._db.execute(
                "INSERT INTO positions (client_order_id, symbol, qty, entry, stop, target, opened_at, checked_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (client_order_id, symbol, qty, price, stop, target, now, now))
            self._db.commit()
            return Position(cur.lastrowid, symbol, qty, price, stop, target, now)

    def find(self, client_order_id: str) -> Position | None:
        with self._lock:
            row = self._db.execute("SELECT %s FROM positions WHERE client_order_id=?" % COLS,
                                   (client_order_id,)).fetchone()
        return Position(*row) if row else None

    def positions(self) -> list[Position]:
        with self._lock:
            rows = self._db.execute("SELECT %s FROM positions WHERE status='open' ORDER BY id" % COLS).fetchall()
        return [Position(*r) for r in rows]

    def history(self) -> list[ClosedTrade]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, symbol, qty, entry, stop, target, opened_at, closed_at, exit_price, reason, pnl "
                "FROM positions WHERE status='closed' ORDER BY closed_at DESC, id DESC").fetchall()
        return [ClosedTrade(*r) for r in rows]

    def tick(self) -> list[ClosedTrade]:
        """Confere stop/alvo/15:55 de cada posição aberta e fecha as que saíram."""
        closed = []
        with self._lock:
            now = self._now()
            now_ny = now.astimezone(NY)
            rows = self._db.execute(
                "SELECT %s, checked_at FROM positions WHERE status='open'" % COLS).fetchall()
            for *pos_cols, checked_at in rows:
                pos = Position(*pos_cols)
                since = datetime.fromisoformat(checked_at)
                low, high = self.feed.range(pos.symbol, since)
                exit_price = reason = None
                if low <= pos.stop:  # stop vence se os dois níveis foram cruzados (pior caso)
                    exit_price, reason = pos.stop, "stop"
                elif high >= pos.target:
                    exit_price, reason = pos.target, "target"
                else:
                    opened_ny = datetime.fromisoformat(pos.opened_at).astimezone(NY)
                    if now_ny.date() > opened_ny.date() or now_ny.time() >= FLAT_BY:
                        exit_price, reason = float(self.feed.last(pos.symbol)), "eod"
                if reason is None:
                    self._db.execute("UPDATE positions SET checked_at=? WHERE id=?", (now.isoformat(), pos.id))
                    continue
                pnl = round((exit_price - pos.entry) * pos.qty, 2)
                self._db.execute(
                    "UPDATE positions SET status='closed', exit_price=?, reason=?, closed_at=?, pnl=? WHERE id=?",
                    (exit_price, reason, now.isoformat(), pnl, pos.id))
                closed.append(ClosedTrade(pos.id, pos.symbol, pos.qty, pos.entry, pos.stop, pos.target,
                                          pos.opened_at, now.isoformat(), exit_price, reason, pnl))
            self._db.commit()
        return closed
