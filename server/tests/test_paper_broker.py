from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.paper.broker import PaperBroker, PaperError

NY = ZoneInfo("America/New_York")


class FakeFeed:
    def __init__(self, price):
        self.prices = {"TSLA": price}
        self.lows = {}
        self.highs = {}

    def last(self, symbol):
        return self.prices[symbol]

    def range(self, symbol, since):
        p = self.prices[symbol]
        return self.lows.get(symbol, p), self.highs.get(symbol, p)


class Clock:
    def __init__(self, hh=10, mm=15):
        self.now = datetime(2026, 10, 19, hh, mm, tzinfo=NY).astimezone(timezone.utc)

    def __call__(self):
        return self.now

    def at(self, hh, mm):
        self.now = datetime(2026, 10, 19, hh, mm, tzinfo=NY).astimezone(timezone.utc)


@pytest.fixture
def env(tmp_path):
    feed, clock = FakeFeed(364.18), Clock()
    broker = PaperBroker(tmp_path / "paper.db", feed, clock, starting_cash=5000.0)
    return broker, feed, clock


def place(broker, cid="o1", qty=8):
    return broker.place_bracket(cid, "TSLA", qty, stop=358.32, target=375.90)


def test_place_bracket_debits_cash(env):
    broker, _, _ = env
    pos = place(broker)
    assert (pos.symbol, pos.qty, pos.entry) == ("TSLA", 8, 364.18)
    assert broker.cash() == pytest.approx(5000 - 8 * 364.18)
    assert len(broker.positions()) == 1


def test_same_client_order_id_does_not_duplicate(env):
    broker, _, _ = env
    a = place(broker)
    b = place(broker)
    assert a.id == b.id and len(broker.positions()) == 1
    assert broker.cash() == pytest.approx(5000 - 8 * 364.18)


def test_zero_qty_rejected(env):
    with pytest.raises(PaperError):
        place(env[0], qty=0)


def test_insufficient_cash_rejected(env):
    with pytest.raises(PaperError) as e:
        place(env[0], qty=20)
    assert "caixa" in str(e.value).lower()


def test_stop_and_target_must_bracket_the_price(env):
    broker, _, _ = env
    with pytest.raises(PaperError):
        broker.place_bracket("o2", "TSLA", 1, stop=370.0, target=375.9)


def test_tick_closes_at_target_with_positive_pnl(env):
    broker, feed, clock = env
    place(broker)
    clock.at(11, 0)
    feed.highs["TSLA"] = 376.0
    closed = broker.tick()
    assert len(closed) == 1 and closed[0].reason == "target"
    assert closed[0].pnl == pytest.approx(8 * (375.90 - 364.18))
    assert broker.positions() == []
    assert broker.cash() == pytest.approx(5000 + closed[0].pnl)


def test_tick_closes_at_stop_with_negative_pnl(env):
    broker, feed, clock = env
    place(broker)
    clock.at(11, 0)
    feed.lows["TSLA"] = 358.0
    closed = broker.tick()
    assert closed[0].reason == "stop" and closed[0].pnl == pytest.approx(-46.88)


def test_gap_through_both_levels_closes_at_stop(env):
    broker, feed, clock = env
    place(broker)
    clock.at(11, 0)
    feed.lows["TSLA"], feed.highs["TSLA"] = 350.0, 380.0
    assert broker.tick()[0].reason == "stop"


def test_tick_does_nothing_inside_the_bracket(env):
    broker, _, clock = env
    place(broker)
    clock.at(11, 0)
    assert broker.tick() == [] and len(broker.positions()) == 1


def test_tick_closes_everything_at_1555_ny(env):
    broker, feed, clock = env
    place(broker)
    feed.prices["TSLA"] = 366.0
    clock.at(15, 55)
    closed = broker.tick()
    assert closed[0].reason == "eod" and closed[0].exit_price == 366.0
    assert closed[0].pnl == pytest.approx(8 * (366.0 - 364.18))


def test_position_left_overnight_is_closed_next_day(env):
    broker, _, clock = env
    place(broker)
    clock.now += timedelta(days=1)
    clock.now = clock.now.replace(hour=14)  # 10:00 NY do dia seguinte
    assert broker.tick()[0].reason == "eod"


def test_history_lists_closed_trades(env):
    broker, feed, clock = env
    place(broker)
    clock.at(11, 0)
    feed.highs["TSLA"] = 376.0
    broker.tick()
    assert [t.symbol for t in broker.history()] == ["TSLA"]


def test_state_survives_restart(tmp_path):
    feed, clock = FakeFeed(364.18), Clock()
    db = tmp_path / "paper.db"
    PaperBroker(db, feed, clock, 5000.0).place_bracket("o1", "TSLA", 8, 358.32, 375.9)
    again = PaperBroker(db, feed, clock, 5000.0)
    assert len(again.positions()) == 1
    assert again.cash() == pytest.approx(5000 - 8 * 364.18)
