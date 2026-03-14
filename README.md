# parkrun-mcp

I wanted to learn MCP so wrote an MCP server to help me interrogate parkrun data in a natural langugae interface, specifically Claude Desktop.

It so far lets me interrogate the parkrun results page, and looks at the list of events (merging in info from the WSW spreadsheet too :) .  To make it fit inside a reasonable context window we slim down the original events.json file quite a bit and it also works a lot better if you are explicit about the country you want to know about in your prompt.

To use this MCP reference it in your `~/Library/Application\ Support/Claude/claude_desktop_config.json` file, this is what works for me:

```
  "mcpServers": {
    "parkrun": {
      "command": "/Users/xxxxx/src/parkrun-mcp/.venv/bin/python",
      "args": [
        "/Users/xxxxx/src/parkrun-mcp/main.py"
      ]
    }
  },
```