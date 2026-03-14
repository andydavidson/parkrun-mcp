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

@mcp.tool()
async def get_events(country_code: int | None = None) -> str:
    """Get parkrun events, optionally filtered by country code.
    
    Common country codes: 97=UK, 3=Australia, 14=Canada, 23=Denmark, 
    30=Finland, 32=France, 33=Germany, 44=Ireland, 57=Italy, 
    67=Netherlands, 74=New Zealand, 82=Poland, 85=South Africa, 
    90=Sweden, 98=USA, 103=Zimbabwe
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://images.parkrun.com/events.json",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15"
            }
        )
        response.raise_for_status()
        data = response.json()
        events = data["events"]["features"]

        if country_code is not None:
            events = [e for e in events if e["properties"]["countrycode"] == country_code and e["properties"]["seriesid"] == 1]
        else:
            events = [e for e in events if e["properties"]["seriesid"] == 1]

        slim = []
        for e in events:
            p = e["properties"]
            obj = {
                "id": e["id"],
                "name": p["eventname"],
                "short": p["EventShortName"],
                "coords": e["geometry"]["coordinates"],
            }
            if country_code is None:
                obj["country"] = p["countrycode"]
            location = p.get("EventLocation")
            if location and location != p["EventShortName"]:
                obj["location"] = location
            slim.append(obj)

        return json.dumps(slim)

if __name__ == "__main__":
    mcp.run()
