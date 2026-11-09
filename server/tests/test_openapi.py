import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def test_openapi_snapshot_is_current(client):
    """Se a API mudar sem atualizar o contrato, falha. Atualize com: python -m app.export_openapi"""
    assert CONTRACT.exists(), "rode: python -m app.export_openapi"
    assert json.loads(CONTRACT.read_text()) == client.app.openapi()


def test_contract_lists_the_paper_routes(client):
    paths = client.app.openapi()["paths"]
    for p in ("/paper/orders", "/paper/positions", "/paper/history", "/paper/account", "/scan/{mode}",
              "/timemachine/run", "/risk/check", "/budget/size"):
        assert p in paths
