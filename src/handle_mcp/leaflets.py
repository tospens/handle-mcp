"""search_leaflets: leaflet offers from every chain in Denmark, through eTilbudsavis' public
search (docs/adr/0016). A chain is not a store: no login, no cart, no product ids.

Two calls: /dealers (every Danish chain, read page by page and kept for a day) and
/offers/search. The search also answers with chains in other countries, so every offer is
kept only when its chain is Danish and its price is in kroner.
"""

from __future__ import annotations

import difflib
import os
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from handle_mcp.models import LeafletOffer
from handle_mcp.stores import StoreError
from handle_mcp.stores._http import request

BASE = "https://api.etilbudsavis.dk/v2"
NAME = "eTilbudsavis"
SEARCH_PAGE = "https://etilbudsavis.dk/soeg/"
DK = ZoneInfo("Europe/Copenhagen")  # leaflets start and end on Danish days
PAGE, MOST_PAGES = 100, 20  # /dealers: 100 per page; DK had 306 chains on 2026-11-17
CHAINS_TTL = 24 * 3600
AHEAD = timedelta(days=7)  # offers that start within a week count: leaflets come out early
OVERFETCH, MOST_FETCHED = 3, 100  # the search ranks every chain; dates and countries filter
UNITS = {"kg": "kg", "l": "l", "pcs": "stk"}  # the API's SI unit -> ours
SHOWN = {"pcs": "stk"}  # the API's unit as written in `size`


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _day(stamp: str) -> date:
    """A stamp such as "2026-11-18T23:00:00+0000" is 19 November in Denmark."""
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").astimezone(DK).date()


def _number(value: Any) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _size(quantity: dict[str, Any]) -> tuple[str | None, Decimal | None, str | None, str | None]:
    """(size as text, amount in the SI unit, our unit, why no unit price)."""
    unit = quantity.get("unit") or {}
    size = quantity.get("size") or {}
    pieces = quantity.get("pieces") or {}
    low, high, symbol = size.get("from"), size.get("to"), unit.get("symbol")
    if low is None or not symbol:
        return None, None, None, "eTilbudsavis oplyser ikke størrelsen."
    shown = SHOWN.get(symbol, symbol)
    text = f"{_number(low)} {shown}" if low == high else f"{_number(low)}-{_number(high)} {shown}"
    count = pieces.get("from") if pieces.get("from") == pieces.get("to") else None
    if count and count > 1:
        text = f"{count} x {text}"
    si = unit.get("si") or {}
    ours = UNITS.get(si.get("symbol", ""))
    if low != high:
        return (
            text,
            None,
            None,
            f"Størrelsen er et spænd ({text}): ingen pris pr. {ours or 'enhed'}.",
        )
    if not ours or not count or not si.get("factor"):
        return (
            text,
            None,
            None,
            "eTilbudsavis oplyser ikke en enhed, der kan regnes pr. kg, l eller stk.",
        )
    return text, Decimal(str(low)) * Decimal(str(si["factor"])) * count, ours, None


def offer(raw: dict[str, Any]) -> LeafletOffer:
    pricing = raw.get("pricing") or {}
    price = _decimal(pricing.get("price"))
    size, amount, unit, reason = _size(raw.get("quantity") or {})
    unit_price = price / amount if price is not None and amount else None
    if price is None:
        reason = "eTilbudsavis oplyser ikke prisen."
    return LeafletOffer(
        chain=(raw.get("dealer") or {}).get("name") or "",
        heading=raw.get("heading") or "",
        description=raw.get("description") or None,
        price=price,
        before_price=_decimal(pricing.get("pre_price")),
        size=size,
        unit_price=unit_price,
        unit=unit if unit_price is not None else None,
        unit_price_reason=None if unit_price is not None else reason,
        valid_from=_day(raw["run_from"]),
        valid_until=_day(raw["run_till"]),
    )


def default_chains() -> list[str]:
    """HANDLE_LEAFLET_CHAINS, e.g. "Netto,Lidl,føtex". Empty: every chain."""
    return [c.strip() for c in os.environ.get("HANDLE_LEAFLET_CHAINS", "").split(",") if c.strip()]


class Leaflets:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=15, headers={"User-Agent": "handle-mcp"})
        self._chains: tuple[float, dict[str, str]] | None = None  # (fetched, id -> name)

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        resp = await request(self._client, "GET", f"{BASE}{path}", NAME, params=params)
        if resp.status_code != 200:
            raise StoreError(f"svarer {resp.status_code}.")
        try:
            return resp.json()
        except ValueError as exc:
            raise StoreError("har ændret format.") from exc

    async def chains(self) -> dict[str, str]:
        """Every Danish chain, id -> name. The first page alone leaves out Netto, Lidl and
        REMA 1000, so every page is read."""
        if self._chains and time.monotonic() - self._chains[0] < CHAINS_TTL:
            return self._chains[1]
        found: dict[str, str] = {}
        for page in range(MOST_PAGES):
            batch = await self._get(
                "/dealers", {"country_id": "DK", "limit": PAGE, "offset": page * PAGE}
            )
            found |= {d["id"]: d["name"] for d in batch if d.get("id") and d.get("name")}
            if len(batch) < PAGE:
                break
        if not found:
            raise StoreError("sendte ingen kæder.")
        self._chains = (time.monotonic(), found)
        return found

    async def _ids(self, names: list[str]) -> list[str]:
        known = await self.chains()
        by_name = {name.casefold(): cid for cid, name in known.items()}
        ids = []
        for name in names:
            if name.casefold() not in by_name:
                close = difflib.get_close_matches(name, known.values(), n=3, cutoff=0.6)
                hint = f" Mente du: {', '.join(close)}?" if close else ""
                raise StoreError(f"kender ikke kæden '{name}'.{hint}")
            ids.append(by_name[name.casefold()])
        return ids

    async def search(
        self, query: str, chains: list[str], limit: int, today: date | None = None
    ) -> dict[str, Any]:
        today = today or datetime.now(DK).date()
        danish = await self.chains()
        params: dict[str, Any] = {
            "query": query,
            "country_id": "DK",
            "limit": min(limit * OVERFETCH, MOST_FETCHED),
        }
        if chains:
            params["dealer_ids"] = ",".join(await self._ids(chains))
        raw = await self._get("/offers/search", params)
        offers = []
        for item in raw:
            pricing = item.get("pricing") or {}
            if item.get("dealer_id") not in danish or pricing.get("currency", "DKK") != "DKK":
                continue
            found = offer(item)
            if found.valid_until >= today and found.valid_from <= today + AHEAD:
                offers.append(found)
        return {
            "offers": offers[:limit],
            "chains": chains or None,  # None: every chain in Denmark
            "url": SEARCH_PAGE + quote(query),
        }
