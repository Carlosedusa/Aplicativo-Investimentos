from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
