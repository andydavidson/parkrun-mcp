from __future__ import annotations
import csv
import io
import math

from bs4 import BeautifulSoup
import httpx

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_4) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15"
)


async def fetch_course_data() -> dict:
    """Fetch WSW course terrain data, keyed by short name."""
    url = (
        "https://docs.google.com/spreadsheets/d/"
        "1mveju_0L4jnvdkvL50ALM4wnMDmyZ6hgQ-LEWAfvA9E/export?format=csv"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        )
        response.raise_for_status()

    lookup = {}
    reader = csv.DictReader(io.StringIO(response.text))
    for row in reader:
        full_name = row.get("parkrun full name", "")
        short = full_name.replace(" parkrun", "").strip()
        lookup[short] = {
            k: v
            for k, v in row.items()
            if k in ("laps", "terrain", "#WhatShoes?", "comments") and v
        }
    return lookup


_course_data: dict | None = None


async def get_course_data() -> dict:
    global _course_data
    if _course_data is None:
        _course_data = await fetch_course_data()
    return _course_data


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


async def fetch_athlete_results(athlete_number: str) -> list[dict]:
    """Return parsed results rows for the given athlete ID."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://www.parkrun.org.uk/parkrunner/{athlete_number}/all/",
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    heading = soup.find(
        "caption",
        string=lambda text: "All" in text and "Results" in text if text else False,
    )
    table = heading.find_parent("table")

    if not table:
        return []

    rows: list[dict] = []
    headers: list[str] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("th")]
        if cells:
            headers = cells
            continue
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cells and headers:
            rows.append(dict(zip(headers, cells)))

    return rows


async def fetch_events(
    country_code: int | None,
    latitude: float | None,
    longitude: float | None,
    limit: int | None,
) -> list[dict]:
    """Return slim event dicts, optionally filtered by country and/or sorted by distance.

    Common country codes: 97=UK, 3=Australia, 14=Canada, 23=Denmark, 30=Finland,
    32=France, 33=Germany, 44=Ireland, 57=Italy, 67=Netherlands, 74=New Zealand,
    82=Poland, 85=South Africa, 90=Sweden, 98=USA, 103=Zimbabwe
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://images.parkrun.com/events.json",
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
        data = response.json()

    events = data["events"]["features"]

    if country_code is not None:
        events = [
            e for e in events
            if e["properties"]["countrycode"] == country_code
            and e["properties"]["seriesid"] == 1
        ]
    else:
        events = [e for e in events if e["properties"]["seriesid"] == 1]

    use_proximity = latitude is not None and longitude is not None
    cd = await get_course_data()

    slim = []
    for e in events:
        p = e["properties"]
        coords = e["geometry"]["coordinates"]
        obj: dict = {
            "id": e["id"],
            "name": p["eventname"],
            "short": p["EventShortName"],
            "coords": coords,
        }
        if country_code is None:
            obj["country"] = p["countrycode"]
        location = p.get("EventLocation")
        if location and location != p["EventShortName"]:
            obj["location"] = location
        terrain = cd.get(p["EventShortName"])
        if terrain:
            obj["terrain"] = terrain
        if use_proximity:
            obj["distance_km"] = round(
                _haversine_km(latitude, longitude, coords[1], coords[0]), 1
            )
        slim.append(obj)

    if use_proximity:
        slim.sort(key=lambda x: x["distance_km"])

    if limit is not None:
        slim = slim[:limit]

    return slim
