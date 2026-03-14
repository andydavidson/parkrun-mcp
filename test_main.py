"""Tests for parkrun MCP server."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(status_code=200, text=None, json_data=None):
    """Build a minimal mock httpx.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.raise_for_status = MagicMock()
    if text is not None:
        mock.text = text
    if json_data is not None:
        mock.json = MagicMock(return_value=json_data)
    return mock


SAMPLE_CSV = """\
parkrun full name,laps,terrain,#WhatShoes?,comments
Bushy parkrun,1,mixed,trail shoes,fast flat course
Victoria Dock parkrun,1,tarmac,,
""".strip()

SAMPLE_EVENTS_JSON = {
    "events": {
        "features": [
            {
                "id": 1,
                "geometry": {"coordinates": [-0.335, 51.411]},
                "properties": {
                    "eventname": "Bushy parkrun",
                    "EventShortName": "Bushy",
                    "EventLocation": "Bushy Park",
                    "countrycode": 97,
                    "seriesid": 1,
                },
            },
            {
                "id": 2,
                "geometry": {"coordinates": [0.023, 51.508]},
                "properties": {
                    "eventname": "Victoria Dock parkrun",
                    "EventShortName": "Victoria Dock",
                    "EventLocation": "Victoria Dock",  # same as short name -> omitted
                    "countrycode": 97,
                    "seriesid": 1,
                },
            },
            # junior parkrun – should be excluded
            {
                "id": 3,
                "geometry": {"coordinates": [0.0, 0.0]},
                "properties": {
                    "eventname": "Bushy junior parkrun",
                    "EventShortName": "Bushy junior",
                    "EventLocation": "Bushy Park",
                    "countrycode": 97,
                    "seriesid": 2,
                },
            },
            # different country
            {
                "id": 4,
                "geometry": {"coordinates": [151.0, -34.0]},
                "properties": {
                    "eventname": "Sydney parkrun",
                    "EventShortName": "Sydney",
                    "EventLocation": "Sydney",
                    "countrycode": 3,
                    "seriesid": 1,
                },
            },
        ]
    }
}

SAMPLE_ATHLETE_HTML = """\
<html><body>
<table>
  <caption>All My Results</caption>
  <tr><th>Run Date</th><th>Event</th><th>Time</th></tr>
  <tr><td>01/01/2024</td><td>Bushy</td><td>20:01</td></tr>
  <tr><td>08/01/2024</td><td>Bushy</td><td>19:45</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# fetch_course_data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_course_data_returns_lookup():
    response = make_response(text=SAMPLE_CSV)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.fetch_course_data()

    assert "Bushy" in result
    assert result["Bushy"]["terrain"] == "mixed"
    assert result["Bushy"]["laps"] == "1"
    assert result["Bushy"]["#WhatShoes?"] == "trail shoes"
    assert "comments" in result["Bushy"]


@pytest.mark.asyncio
async def test_fetch_course_data_skips_empty_fields():
    response = make_response(text=SAMPLE_CSV)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.fetch_course_data()

    # Victoria Dock has empty comments and #WhatShoes? - they should be absent
    assert "comments" not in result.get("Victoria Dock", {})
    assert "#WhatShoes?" not in result.get("Victoria Dock", {})


@pytest.mark.asyncio
async def test_fetch_course_data_strips_parkrun_suffix():
    """'Bushy parkrun' in the CSV should produce key 'Bushy'."""
    response = make_response(text=SAMPLE_CSV)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.fetch_course_data()

    assert "Bushy" in result
    assert "Bushy parkrun" not in result


# ---------------------------------------------------------------------------
# get_course_data (caching)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_course_data_caches_result():
    """fetch_course_data should only be called once even if get_course_data is awaited twice."""
    main.course_data = None  # reset cache

    response = make_response(text=SAMPLE_CSV)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        first = await main.get_course_data()
        second = await main.get_course_data()

    assert first is second
    assert mock_client.get.call_count == 1

    main.course_data = None  # clean up


# ---------------------------------------------------------------------------
# get_athlete_results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_athlete_results_parses_table():
    response = make_response(text=SAMPLE_ATHLETE_HTML)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_athlete_results("12345")

    rows = json.loads(result)
    assert len(rows) == 2
    assert rows[0] == {"Run Date": "01/01/2024", "Event": "Bushy", "Time": "20:01"}
    assert rows[1]["Time"] == "19:45"


@pytest.mark.asyncio
async def test_get_athlete_results_uses_correct_url():
    response = make_response(text=SAMPLE_ATHLETE_HTML)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await main.get_athlete_results("99999")

    called_url = mock_client.get.call_args[0][0]
    assert "99999" in called_url
    assert "parkrun.org.uk" in called_url


@pytest.mark.asyncio
async def test_get_athlete_results_no_table():
    html = "<html><body><p>No results here</p></body></html>"
    response = make_response(text=html)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(Exception):
            # heading.find_parent will raise AttributeError when heading is None
            await main.get_athlete_results("00000")


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_course_cache():
    """Ensure course_data cache is clear before each test."""
    main.course_data = None
    yield
    main.course_data = None


def _make_events_mock(course_text=SAMPLE_CSV, events_json=SAMPLE_EVENTS_JSON):
    """Return a mock httpx.AsyncClient that handles both network calls."""
    events_response = make_response(json_data=events_json)
    course_response = make_response(text=course_text)

    async def fake_get(url, **kwargs):
        if "parkrun.com/events" in url:
            return events_response
        return course_response  # Google Sheets CSV

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=fake_get)
    return mock_client


@pytest.mark.asyncio
async def test_get_events_excludes_junior_parkruns():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events()

    events = json.loads(result)
    names = [e["name"] for e in events]
    assert "Bushy junior parkrun" not in names


@pytest.mark.asyncio
async def test_get_events_filters_by_country_code():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events(country_code=97)

    events = json.loads(result)
    assert all(e.get("country") is None for e in events)  # country field omitted when filtered
    names = [e["name"] for e in events]
    assert "Sydney parkrun" not in names
    assert "Bushy parkrun" in names


@pytest.mark.asyncio
async def test_get_events_includes_country_when_no_filter():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events()

    events = json.loads(result)
    assert all("country" in e for e in events)


@pytest.mark.asyncio
async def test_get_events_omits_location_when_same_as_short_name():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events(country_code=97)

    events = json.loads(result)
    victoria_dock = next(e for e in events if e["name"] == "Victoria Dock parkrun")
    assert "location" not in victoria_dock


@pytest.mark.asyncio
async def test_get_events_includes_location_when_different():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events(country_code=97)

    events = json.loads(result)
    bushy = next(e for e in events if e["name"] == "Bushy parkrun")
    assert bushy["location"] == "Bushy Park"


@pytest.mark.asyncio
async def test_get_events_merges_terrain_data():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events(country_code=97)

    events = json.loads(result)
    bushy = next(e for e in events if e["name"] == "Bushy parkrun")
    assert "terrain" in bushy
    assert bushy["terrain"]["terrain"] == "mixed"


@pytest.mark.asyncio
async def test_get_events_no_terrain_when_not_in_spreadsheet():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events(country_code=3)  # Australia / Sydney

    events = json.loads(result)
    sydney = next(e for e in events if e["name"] == "Sydney parkrun")
    assert "terrain" not in sydney


@pytest.mark.asyncio
async def test_get_events_result_has_required_fields():
    mock_client = _make_events_mock()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await main.get_events(country_code=97)

    events = json.loads(result)
    for event in events:
        assert "id" in event
        assert "name" in event
        assert "short" in event
        assert "coords" in event
