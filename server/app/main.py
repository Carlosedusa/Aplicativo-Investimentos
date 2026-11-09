import secrets

from fastapi import Depends, FastAPI, HTTPException, Request

from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Day Trader API")
    app.state.settings = settings

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
                token.encode(), settings.api_token.encode()):
            raise HTTPException(401, "Token inválido.")

    app.state.require_token = require_token

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/auth/check", dependencies=[Depends(require_token)])
    def auth_check():
        return {"ok": True}

    return app
