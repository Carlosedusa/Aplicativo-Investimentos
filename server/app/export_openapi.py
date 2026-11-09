"""Grava o contrato da API em docs/api/openapi.json (o app Swift seguirá este arquivo)."""
import json
import tempfile
from pathlib import Path

from .config import Settings
from .main import create_app

OUT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(api_token="x", workdir=Path(tmp), monitor_interval=0))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
        print("gravado", OUT)
