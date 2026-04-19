from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

import tomli_w
from mcp import types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from .auth import BearerAuthMiddleware
from .oauth import handle_authorize, handle_metadata, handle_token
from .queries import fetch_athlete_results, fetch_events

log = logging.getLogger(__name__)

mcp = Server("parkrun")


# ---------------------------------------------------------------------------
# TOML serialisation helpers
# ---------------------------------------------------------------------------

def _clean(obj: Any) -> Any:
    """Recursively prepare data for tomli_w."""
    if obj is None:
        return ""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float, str)):
        return obj
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_clean(item) for item in obj]
    return str(obj)


def _dump(data: dict) -> str:
    """Serialise to TOML, returning an error string on failure."""
    try:
        return tomli_w.dumps(_clean(data))
    except Exception as exc:
        return f'error = "TOML serialisation failed: {exc}"\n'


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@mcp.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_athlete_results",
            description=(
                "Get parkrun results history for an athlete by their ID number. "
                "Returns a list of results with fields: Run Date, Event, Time, "
                "and any other columns present in the athlete's results table."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "athlete_number": {
                        "type": "string",
                        "description": "The athlete's parkrun ID number",
                    },
                },
                "required": ["athlete_number"],
            },
        ),
        types.Tool(
            name="get_events",
            description=(
                "Get parkrun events, optionally filtered by country code and/or "
                "sorted by proximity to a location. "
                "Returns id, name, short, coords ([lon, lat]), and optionally: "
                "country (omitted when country_code filter is applied), "
                "location (omitted when identical to short name), "
                "terrain (laps, terrain type, '#WhatShoes?' shoe recommendation, comments), "
                "distance_km (included and sorted nearest-first when lat/lon are provided). "
                "Common country codes: 97=UK, 3=Australia, 14=Canada, 23=Denmark, "
                "30=Finland, 32=France, 33=Germany, 44=Ireland, 57=Italy, "
                "67=Netherlands, 74=New Zealand, 82=Poland, 85=South Africa, "
                "90=Sweden, 98=USA, 103=Zimbabwe."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "country_code": {
                        "type": "integer",
                        "description": "Filter events to this country only",
                    },
                    "latitude": {
                        "type": "number",
                        "description": "Latitude for proximity search; requires longitude",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Longitude for proximity search; requires latitude",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                    },
                },
                "required": [],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

@mcp.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    args = arguments or {}
    try:
        result = await _dispatch(name, args)
        return [types.TextContent(type="text", text=result)]
    except Exception as exc:
        log.exception("Tool %s failed", name)
        return [types.TextContent(
            type="text",
            text=_dump({"error": str(exc), "tool": name}),
        )]


async def _dispatch(name: str, args: dict) -> str:
    if name == "get_athlete_results":
        athlete_number = str(args["athlete_number"])
        rows = await fetch_athlete_results(athlete_number)
        return _dump({"results": rows})

    if name == "get_events":
        country_code = int(args["country_code"]) if args.get("country_code") is not None else None
        latitude = float(args["latitude"]) if args.get("latitude") is not None else None
        longitude = float(args["longitude"]) if args.get("longitude") is not None else None
        limit = int(args["limit"]) if args.get("limit") is not None else None
        events = await fetch_events(country_code, latitude, longitude, limit)
        return _dump({"events": events})

    return _dump({"error": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Any:
    session_manager = StreamableHTTPSessionManager(
        app=mcp,
        event_store=None,
        json_response=False,
        stateless=True,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with session_manager.run():
            yield

    async def handle_mcp(scope: Any, receive: Any, send: Any) -> None:
        # Mount("/") strips the leading "/" — restore it so the MCP handler sees "/"
        if scope.get("type") == "http" and not scope.get("path"):
            scope = {**scope, "path": "/"}
        await session_manager.handle_request(scope, receive, send)

    starlette_app = Starlette(
        routes=[
            Route("/.well-known/oauth-authorization-server", endpoint=handle_metadata),
            Route("/authorize", endpoint=handle_authorize, methods=["GET", "POST"]),
            Route("/token", endpoint=handle_token, methods=["POST"]),
            Mount("/", app=handle_mcp),
        ],
        lifespan=lifespan,
    )

    return BearerAuthMiddleware(starlette_app)
