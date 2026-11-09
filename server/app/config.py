import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    api_token: str
    workdir: Path
    starting_cash: float = 5000.0

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("API_TOKEN", "")
        if not token:
            raise RuntimeError("Defina a variável de ambiente API_TOKEN.")
        return cls(
            api_token=token,
            workdir=Path(os.environ.get("WORKDIR", "data")).resolve(),
            starting_cash=float(os.environ.get("STARTING_CASH", "5000")),
        )
