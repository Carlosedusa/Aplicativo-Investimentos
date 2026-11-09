from tests.conftest import AUTH


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_protected_route_without_token_is_401(client):
    assert client.get("/auth/check").status_code == 401


def test_protected_route_with_wrong_token_is_401(client):
    assert client.get("/auth/check", headers={"Authorization": "Bearer x"}).status_code == 401


def test_auth_check_accepts_valid_token(client):
    assert client.get("/auth/check", headers=AUTH).status_code == 200
