# parkrun-mcp

An MCP server that lets you interrogate parkrun data through a natural language interface (Claude.ai, Claude Desktop, or the Claude API).

**Tools provided:**

- `get_athlete_results` — fetch a runner's complete results history by athlete ID
- `get_events` — list parkrun events worldwide, filterable by country, sortable by proximity; enriched with terrain data from the [WSW spreadsheet](https://docs.google.com/spreadsheets/d/1mveju_0L4jnvdkvL50ALM4wnMDmyZ6hgQ-LEWAfvA9E)

Results are returned as TOML. Tip: be explicit about the country you want — it keeps the response within a sensible context window.

---

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

---

## Development setup

```bash
git clone https://github.com/andydavidson/parkrun-mcp.git
cd parkrun-mcp

# Install all dependencies (including dev)
uv sync --all-groups

# Run the tests
uv run pytest
```

The server reads tokens from `config/mcp_tokens.toml` at startup. You need this file before the server will accept connections (see [Token management](#token-management) below).

### Running locally

```bash
uv run python -m parkrun_mcp               # binds to 127.0.0.1:8003
uv run python -m parkrun_mcp --port 9000   # custom port
```

Once running, test it directly:

```bash
curl -s -H "Authorization: Bearer <your-token>" http://127.0.0.1:8003/
```

---

## Token management

Tokens live in `config/mcp_tokens.toml`, which is gitignored. Copy the example and add real tokens:

```bash
cp config/mcp_tokens.toml.example config/mcp_tokens.toml
```

Generate a token for each user:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Edit `config/mcp_tokens.toml`:

```toml
[users.alice]
token       = "the-hex-string-you-just-generated"
description = "Alice Smith"
```

Tokens are loaded once at startup via `lru_cache`. **Restart the process** to pick up changes.

---

## Production deployment

### systemd service

Create `/etc/systemd/system/parkrun-mcp.service`:

```ini
[Unit]
Description=parkrun MCP Server
After=network.target

[Service]
Type=simple
User=your-service-user
WorkingDirectory=/opt/parkrun-mcp

ExecStart=/opt/parkrun-mcp/.venv/bin/uvicorn \
    parkrun_mcp.server:create_app \
    --factory \
    --host 127.0.0.1 \
    --port 8003 \
    --workers 1

Restart=on-failure
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=parkrun-mcp

[Install]
WantedBy=multi-user.target
```

> Always use `--workers 1`. SSE connections are long-lived; multiple workers would split connections across processes with no shared state.

```bash
sudo systemctl enable --now parkrun-mcp
sudo journalctl -u parkrun-mcp -f
```

### nginx

Add these blocks inside your `server {}` context (replace `yourdomain.com` as needed):

```nginx
upstream parkrun_mcp {
    server 127.0.0.1:8003;
    keepalive 8;
}

# OAuth discovery endpoints — served from the domain root
location = /.well-known/oauth-authorization-server {
    proxy_pass http://parkrun_mcp;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location = /authorize {
    proxy_pass http://parkrun_mcp;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location = /token {
    proxy_pass http://parkrun_mcp;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Redirect /mcp → /mcp/ preserving POST method
location = /mcp {
    return 308 https://$host/mcp/;
}

# MCP endpoint — SSE requires buffering off and long timeouts
location /mcp/ {
    proxy_pass         http://parkrun_mcp/;
    proxy_buffering    off;
    proxy_cache        off;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    chunked_transfer_encoding on;
    proxy_http_version 1.1;
    proxy_set_header   Connection "";
    proxy_set_header   Host $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
```

---

## Connecting to Claude.ai

**Option A — OAuth flow (recommended):**

1. Settings → Model Context Protocol → Add remote server
2. URL: `https://yourdomain.com/mcp/`
3. Claude.ai detects the OAuth metadata endpoint and prompts you to log in — paste your bearer token into the form

**Option B — direct bearer token:**

1. Settings → Model Context Protocol → Add remote server
2. URL: `https://yourdomain.com/mcp/`
3. Custom header — Name: `Authorization`, Value: `Bearer <token>`

## Connecting via the Claude API

```python
import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-4-7",
    max_tokens=4096,
    tools=[{
        "type": "mcp",
        "server": {
            "type": "url",
            "url": "https://yourdomain.com/mcp/",
            "authorization_token": "your-token",
        },
    }],
    messages=[{"role": "user", "content": "What parkrun events are near Oxford?"}],
    betas=["mcp-client-2025-04-04"],
)
```

---

## Testing

```bash
uv run pytest                  # run all tests
uv run pytest -v               # verbose output
uv run pytest -k fetch_events  # run tests matching a pattern
```

Tests mock all HTTP calls — no network access required. The test suite covers:

- `fetch_course_data` — CSV parsing, key normalisation, empty-field filtering
- `get_course_data` — lazy-load caching (single fetch across multiple calls)
- `fetch_athlete_results` — HTML table parsing, URL construction, missing-table handling
- `fetch_events` — country filtering, junior exclusion, proximity sorting, terrain merging, field presence

---

## Repository structure

```
parkrun_mcp/
├── auth.py         # Pure-ASGI bearer-token middleware
├── oauth.py        # OAuth 2.0 + PKCE authorisation endpoints
├── queries.py      # Data-fetching functions (parkrun.org.uk, events.json, WSW sheet)
├── server.py       # MCP tool definitions, TOML serialisation, Starlette app factory
└── __main__.py     # Entry point: python -m parkrun_mcp
config/
├── mcp_tokens.toml.example   # Checked in — copy to mcp_tokens.toml and add real tokens
└── mcp_tokens.toml           # Gitignored — never commit
test_main.py
pyproject.toml
```

### Branching

```bash
# Create a feature branch
git checkout -b your-branch-name

# After merging, clean up
git checkout main && git pull
git branch -d your-branch-name
```

The `main` branch is the stable branch. Open a PR against `main` for all changes.
