from __future__ import annotations
import base64
import hashlib
import os
import time
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from .auth import validate_token

# In-memory auth-code store: code -> {token, code_challenge, expires_at}
# Resets on process restart — fine for single-worker deployments.
_codes: dict[str, dict] = {}

_FORM = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>parkrun MCP &#8212; Authorise</title>
  <style>
    body {{ font-family: sans-serif; max-width: 420px; margin: 4em auto; padding: 1em; }}
    input[type=password] {{ width: 100%; padding: .4em; margin: .5em 0; box-sizing: border-box; }}
    button {{ padding: .5em 1.5em; margin-top: .5em; }}
  </style>
</head>
<body>
  <h1>parkrun MCP</h1>
  <p>Enter your API token to grant Claude.ai access to your parkrun MCP server.</p>
  <form method="post">
    <input type="hidden" name="state"          value="{state}">
    <input type="hidden" name="code_challenge"  value="{code_challenge}">
    <input type="hidden" name="redirect_uri"   value="{redirect_uri}">
    <input type="hidden" name="client_id"      value="{client_id}">
    <label>Token:<br>
      <input type="password" name="token" required autofocus>
    </label><br>
    <button type="submit">Authorise</button>
  </form>
</body>
</html>
"""


async def handle_metadata(request: Request) -> JSONResponse:
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
    })


async def handle_authorize(request: Request) -> HTMLResponse | RedirectResponse:
    if request.method == "GET":
        p = dict(request.query_params)
        html = _FORM.format(
            state=p.get("state", ""),
            code_challenge=p.get("code_challenge", ""),
            redirect_uri=p.get("redirect_uri", ""),
            client_id=p.get("client_id", ""),
        )
        return HTMLResponse(html)

    # POST — form submission
    form = await request.form()
    token = str(form.get("token", ""))
    state = str(form.get("state", ""))
    code_challenge = str(form.get("code_challenge", ""))
    redirect_uri = str(form.get("redirect_uri", ""))

    if not validate_token(token):
        return HTMLResponse(
            "<p style='color:red'>Invalid token — please go back and try again.</p>",
            status_code=400,
        )

    code = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    _codes[code] = {
        "token": token,
        "code_challenge": code_challenge,
        "expires_at": time.time() + 600,  # 10 minutes
    }

    location = redirect_uri + "?" + urlencode({"code": code, "state": state})
    return RedirectResponse(location, status_code=302)


async def handle_token(request: Request) -> JSONResponse:
    form = await request.form()
    code = str(form.get("code", ""))
    code_verifier = str(form.get("code_verifier", ""))

    entry = _codes.pop(code, None)
    if entry is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    if time.time() > entry["expires_at"]:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "authorization code expired"},
            status_code=400,
        )

    # PKCE S256: code_challenge == BASE64URL(SHA256(code_verifier))
    digest = hashlib.sha256(code_verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    if expected != entry["code_challenge"]:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "PKCE verification failed"},
            status_code=400,
        )

    return JSONResponse({
        "access_token": entry["token"],
        "token_type": "bearer",
        "expires_in": 315360000,  # ~10 years; tokens are revoked by removing from config
    })
