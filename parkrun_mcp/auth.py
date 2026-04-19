from __future__ import annotations
import tomllib
from functools import lru_cache
from pathlib import Path
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_tokens.toml"


@lru_cache(maxsize=1)
def _load_tokens() -> dict[str, str]:
    """Return {token: username} from the TOML config file."""
    with open(_CONFIG_PATH, "rb") as fh:
        config = tomllib.load(fh)
    return {
        user["token"]: name
        for name, user in config.get("users", {}).items()
    }


def validate_token(token: str) -> str | None:
    return _load_tokens().get(token)


_EXEMPT = frozenset({
    "/.well-known/oauth-authorization-server",
    "/authorize",
    "/token",
})


class BearerAuthMiddleware:
    """Pure-ASGI middleware — does not interfere with SSE streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path not in _EXEMPT:
                headers = dict(scope.get("headers", []))
                raw_auth: bytes = headers.get(b"authorization", b"")
                auth = raw_auth.decode(errors="replace")
                if not auth.startswith("Bearer "):
                    await Response("Unauthorized\n", status_code=401)(scope, receive, send)
                    return
                token = auth[7:].strip()
                if not validate_token(token):
                    await Response("Forbidden\n", status_code=403)(scope, receive, send)
                    return
        await self.app(scope, receive, send)
