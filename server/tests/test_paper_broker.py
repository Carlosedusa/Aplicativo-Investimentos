from datetime import datetime, timedelta, timezone

import pytest

from app.paper.broker import PaperBroker, PaperError
from tests.fakes import NY, Clock, FakeFeed

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


def test_find_by_client_order_id(env):
    broker, _, _ = env
    assert broker.find("o1") is None
    pos = place(broker)
    assert broker.find("o1") == pos


def test_one_failing_quote_does_not_block_other_positions(env):
    broker, feed, clock = env
    feed.prices["XYZ"] = 10.0
    place(broker)
    broker.place_bracket("o2", "XYZ", 5, stop=9.0, target=12.0)
    feed.bad.add("XYZ")
    clock.at(11, 0)
    feed.highs["TSLA"] = 376.0
    closed = broker.tick()
    assert [t.symbol for t in closed] == ["TSLA"]
    assert [p.symbol for p in broker.positions()] == ["XYZ"]


def test_slow_quote_does_not_hold_the_book_lock(env):
    import threading
    broker, feed, clock = env
    place(broker)
    clock.at(11, 0)
    entered, release = threading.Event(), threading.Event()

    def hold():
        entered.set()
        release.wait(3)

    feed.on_range = hold
    t = threading.Thread(target=broker.tick)
    t.start()
    assert entered.wait(2)
    done = []
    reader = threading.Thread(target=lambda: done.append(broker.positions()))
    reader.start()
    reader.join(1)
    release.set()
    t.join(3)
    assert done, "positions() ficou preso esperando a cotação"


def test_swing_position_survives_overnight_and_exits_on_deadline(tmp_path):
    from datetime import datetime, timedelta, timezone
    from app.paper.broker import PaperBroker
    from tests.fakes import FakeFeed
    t = {"now": datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)}
    feed = FakeFeed(30.0); feed.prices["PETR4"] = 30.0
    b = PaperBroker(tmp_path / "p.db", feed, lambda: t["now"], 5000)
    b.place_bracket("a", "PETR4", 10, 28.0, 36.0, horizon_days=3)
    t["now"] += timedelta(days=1); assert b.tick() == [] and len(b.positions()) == 1      # dormiu posicionado
    t["now"] += timedelta(days=3)                                                          # 3 dias úteis depois
    closed = b.tick()
    assert len(closed) == 1 and closed[0].reason == "prazo"
