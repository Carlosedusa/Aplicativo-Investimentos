from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


class FakeFeed:
    def __init__(self, price):
        self.prices = {"TSLA": price}
        self.lows = {}
        self.highs = {}
        self.bad = set()      # símbolos cuja cotação falha
        self.on_range = None  # gancho chamado dentro de range()

    def last(self, symbol):
        from app.paper.prices import PriceError
        if symbol in self.bad:
            raise PriceError("Sem cotação de %s agora." % symbol)
        return self.prices[symbol]

    def candles(self, symbol, interval="5m", limit=40):
        p = self.prices[symbol]
        return [{"t": 1_700_000_000 + 300 * i, "o": p, "h": p + 1, "l": p - 1, "c": p} for i in range(3)]

    def range(self, symbol, since):
        from app.paper.prices import PriceError
        if self.on_range:
            self.on_range()
        if symbol in self.bad:
            raise PriceError("Sem cotação de %s agora." % symbol)
        p = self.prices[symbol]
        return self.lows.get(symbol, p), self.highs.get(symbol, p)


class Clock:
    def __init__(self, hh=10, mm=15):
        self.now = datetime(2026, 10, 19, hh, mm, tzinfo=NY).astimezone(timezone.utc)

    def __call__(self):
        return self.now

    def at(self, hh, mm):
        self.now = datetime(2026, 10, 19, hh, mm, tzinfo=NY).astimezone(timezone.utc)
