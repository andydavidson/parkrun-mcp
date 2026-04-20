import argparse
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="parkrun MCP server (HTTP/OAuth)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8003, help="Port to listen on (default: 8003)")
    args = parser.parse_args()

    uvicorn.run(
        "parkrun_mcp.server:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    main()
