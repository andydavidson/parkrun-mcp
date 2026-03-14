import httpx
import json
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("parkrun")


@mcp.tool()
async def get_athlete_results(athlete_number: str) -> str:
    """Get parkrun results history for a given athlete ID number."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://www.parkrun.org.uk/parkrunner/{athlete_number}/all/",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15"
            }
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        heading = soup.find("caption", string=lambda text: "All" in text and "Results" in text if text else False)
        table = heading.find_parent("table")

        if not table:
            return "No results table found"

        rows = []
        headers = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("th")]
            if cells:
                headers = cells
                continue
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells and headers:
                row = dict(zip(headers, cells))
                rows.append(row)

        return json.dumps(rows, indent=2)

if __name__ == "__main__":
    mcp.run()
