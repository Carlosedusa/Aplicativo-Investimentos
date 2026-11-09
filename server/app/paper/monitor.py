import logging
import threading

from .broker import ClosedTrade, PaperBroker

log = logging.getLogger("paper.monitor")


class Monitor:
    """Chama broker.tick() em intervalos; erro de rede nunca derruba o servidor."""

    def __init__(self, broker: PaperBroker, interval: float):
        self.broker, self.interval = broker, interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> list[ClosedTrade]:
        try:
            return self.broker.tick()
        except Exception as e:
            log.warning("tick falhou: %s", e)
            return []

    def start(self) -> None:
        if self.interval <= 0 or self._thread:
            return

        def loop():
            while not self._stop.wait(self.interval):
                self.run_once()

        self._thread = threading.Thread(target=loop, daemon=True, name="paper-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
