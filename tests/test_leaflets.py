"""search_leaflets: eTilbudsavis against real captures (httpx.MockTransport)."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from handle_mcp import leaflets, read_tools
from handle_mcp.stores import StoreError

FIXTURES = Path(__file__).parent / "fixtures" / "etilbudsavis"
TODAY = date(2026, 11, 17)
CHAINS = ["Netto", "Lidl", "føtex", "REMA 1000", "Bilka", "SuperBrugsen"]


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Api:
    """The two endpoints, from the captures. Records every request."""

    def __init__(self, search: str = "search_kaffe.json") -> None:
        self.search = search
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v2/dealers":
            return httpx.Response(
                200, json=_fixture(f"dealers_offset_{request.url.params['offset']}.json")
            )
        if request.url.path == "/v2/offers/search":
            return httpx.Response(200, json=_fixture(self.search))
        return httpx.Response(404)

    def client(self) -> leaflets.Leaflets:
        return leaflets.Leaflets(httpx.AsyncClient(transport=httpx.MockTransport(self)))


async def test_every_page_of_chains_is_read():
    api = Api()
    chains = await api.client().chains()
    assert len(chains) == 306
    assert {"Netto", "Lidl", "REMA 1000"} <= set(chains.values())  # none on the first page
    assert [r.url.params["offset"] for r in api.requests] == ["0", "100", "200", "300"]


async def test_chains_are_kept_between_searches():
    api = Api()
    client = api.client()
    await client.search("kaffe", [], 5, today=TODAY)
    await client.search("kaffe", [], 5, today=TODAY)
    assert sum(r.url.path == "/v2/dealers" for r in api.requests) == 4


async def test_chain_names_become_ids_and_filter_the_search():
    api = Api("search_kaffe_chains.json")
    found = await api.client().search("kaffe", CHAINS, 50, today=TODAY)
    search = next(r for r in api.requests if r.url.path == "/v2/offers/search")
    assert search.url.params["dealer_ids"] == "9ba51,71c90,bdf5A,11deC,93f13,0b1e8"
    assert search.url.params["country_id"] == "DK"
    assert {o.chain for o in found["offers"]} <= set(CHAINS)
    assert found["chains"] == CHAINS


async def test_chain_names_ignore_case():
    api = Api("search_kaffe_chains.json")
    await api.client().search("kaffe", ["rema 1000", "FØTEX"], 5, today=TODAY)
    search = next(r for r in api.requests if r.url.path == "/v2/offers/search")
    assert search.url.params["dealer_ids"] == "11deC,bdf5A"


async def test_an_unknown_chain_says_what_it_may_be():
    with pytest.raises(StoreError, match="kender ikke kæden 'Neto'.*Netto"):
        await Api().client().search("kaffe", ["Neto"], 5, today=TODAY)


async def test_foreign_chains_and_currencies_are_left_out():
    raw = _fixture("search_kaffe.json")
    assert {o["pricing"]["currency"] for o in raw} > {"DKK"}  # the capture has NOK and SEK
    found = await Api().client().search("kaffe", [], 50, today=TODAY)
    danish = set((await Api().client().chains()).values())
    assert found["offers"]
    assert all(o.chain in danish for o in found["offers"])
    assert found["chains"] is None


async def test_the_search_asks_for_more_than_the_limit():
    api = Api()
    await api.client().search("kaffe", [], 20, today=TODAY)
    search = next(r for r in api.requests if r.url.path == "/v2/offers/search")
    assert search.url.params["limit"] == "60"
    await api.client().search("kaffe", [], 50, today=TODAY)
    search = [r for r in api.requests if r.url.path == "/v2/offers/search"][-1]
    assert search.url.params["limit"] == "100"  # the API's most


async def test_offers_valid_today_or_within_a_week():
    found = await Api("search_kaffe_chains.json").client().search("kaffe", CHAINS, 50, TODAY)
    assert found["offers"]
    for o in found["offers"]:
        assert o.valid_until >= TODAY
        assert o.valid_from <= date(2026, 11, 24)
    later = (
        await Api("search_kaffe_chains.json")
        .client()
        .search("kaffe", CHAINS, 50, date(2026, 11, 22))
    )
    assert all(o.valid_until >= date(2026, 11, 22) for o in later["offers"])
    assert len(later["offers"]) < len(found["offers"])  # the week-47 leaflets are over


async def test_the_limit_cuts_the_answer():
    found = await Api("search_kaffe_chains.json").client().search("kaffe", CHAINS, 3, TODAY)
    assert len(found["offers"]) == 3


def test_days_are_danish():
    assert leaflets._day("2026-11-18T23:00:00+0000") == date(2026, 11, 19)
    assert leaflets._day("2026-11-21T22:59:59+0000") == date(2026, 11, 21)


def _raw(unit: str, si: str, factor: float, low, high, pieces: int = 1, price=55, pre=None):
    return {
        "heading": "Kaffe",
        "description": None,
        "pricing": {"price": price, "pre_price": pre, "currency": "DKK"},
        "quantity": {
            "unit": {"symbol": unit, "si": {"symbol": si, "factor": factor}},
            "size": {"from": low, "to": high},
            "pieces": {"from": pieces, "to": pieces, "min": None, "max": None},
        },
        "dealer": {"name": "Netto"},
        "run_from": "2026-11-13T23:00:00+0000",
        "run_till": "2026-11-20T22:59:59+0000",
    }


def test_unit_price_per_kg():
    o = leaflets.offer(_raw("g", "kg", 0.001, 400, 400, price=30))
    assert (o.size, o.unit, o.unit_price, o.unit_price_reason) == ("400 g", "kg", 75, None)


def test_unit_price_counts_the_pieces():
    o = leaflets.offer(_raw("g", "kg", 0.001, 250, 250, pieces=2, price=50))
    assert (o.size, o.unit_price, o.unit) == ("2 x 250 g", 100, "kg")


def test_unit_price_per_litre_and_piece():
    assert leaflets.offer(_raw("cl", "l", 0.01, 70, 70, price=140)).unit_price == 200
    pack = leaflets.offer(_raw("pcs", "pcs", 1, 16, 16, price=40))
    assert (pack.size, pack.unit, pack.unit_price) == ("16 stk", "stk", Decimal("2.5"))


def test_a_size_range_has_no_unit_price_and_says_why():
    o = leaflets.offer(_raw("g", "kg", 0.001, 100, 500))
    assert o.size == "100-500 g"
    assert o.unit_price is None and o.unit is None
    assert o.unit_price_reason == "Størrelsen er et spænd (100-500 g): ingen pris pr. kg."


def test_money_and_dates():
    o = leaflets.offer(_raw("g", "kg", 0.001, 400, 400, price=44.95, pre=59.9))
    assert (o.price, o.before_price) == (Decimal("44.95"), Decimal("59.9"))
    assert (o.valid_from, o.valid_until) == (date(2026, 11, 14), date(2026, 11, 20))


def test_default_chains_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("HANDLE_LEAFLET_CHAINS", " Netto, REMA 1000 ,,føtex")
    assert leaflets.default_chains() == ["Netto", "REMA 1000", "føtex"]
    monkeypatch.delenv("HANDLE_LEAFLET_CHAINS")
    assert leaflets.default_chains() == []


async def test_tool_answers_json_with_money_as_strings(monkeypatch):
    monkeypatch.setattr(read_tools, "_leaflets", Api("search_kaffe_chains.json").client())
    monkeypatch.setenv("HANDLE_LEAFLET_CHAINS", ",".join(CHAINS))
    out = await read_tools.search_leaflets("kaffe", limit=2)
    first = out["offers"][0]
    assert isinstance(first["price"], str) and first["price"].count(".") == 1
    assert len(first["price"].split(".")[1]) == 2
    assert out["url"] == "https://etilbudsavis.dk/soeg/kaffe"
    assert out["chains"] == CHAINS


async def test_tool_error_is_danish_and_named(monkeypatch):
    monkeypatch.setattr(read_tools, "_leaflets", Api().client())
    with pytest.raises(ToolError, match="^eTilbudsavis: kender ikke kæden 'Lild'"):
        await read_tools.search_leaflets("kaffe", chains=["Lild"])


async def test_a_failing_api_is_a_clear_error(monkeypatch):
    def down(_request):
        return httpx.Response(503)

    client = leaflets.Leaflets(httpx.AsyncClient(transport=httpx.MockTransport(down)))
    monkeypatch.setattr("handle_mcp.stores._http.asyncio.sleep", _no_sleep)
    monkeypatch.setattr(read_tools, "_leaflets", client)
    with pytest.raises(ToolError, match="^eTilbudsavis: eTilbudsavis svarer 503"):
        await read_tools.search_leaflets("kaffe", chains=[])


async def _no_sleep(_seconds):
    return None
