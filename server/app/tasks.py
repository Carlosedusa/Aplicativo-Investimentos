import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class TaskManager:
    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, fn: Callable[[], dict]) -> str:
        tid = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[tid] = {"id": tid, "status": "pending", "result": None, "error": None}

        def run():
            self._set(tid, status="running")
            try:
                self._set(tid, status="done", result=fn())
            except Exception as e:  # erro vira estado da tarefa, nunca derruba o servidor
                self._set(tid, status="error", error=str(e) or e.__class__.__name__)

        self._pool.submit(run)
        return tid

    def _set(self, tid: str, **fields) -> None:
        with self._lock:
            self._tasks[tid].update(fields)

    def get(self, tid: str) -> dict | None:
        with self._lock:
            t = self._tasks.get(tid)
            return dict(t) if t else None
