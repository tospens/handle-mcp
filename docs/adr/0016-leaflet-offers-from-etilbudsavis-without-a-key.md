# 0016: Leaflet offers come from eTilbudsavis' public search, without a key

`search_leaflets` finds leaflet offers from every chain in Denmark through the search eTilbudsavis' own website uses (`api.etilbudsavis.dk/v2`: `/offers/search` and `/dealers`), with no API key. It sends no location: chain leaflets are national, so it searches all of Denmark and keeps the chains asked for.

## Why

Tjek's official API needs a key that is only given after contacting services@tjek.com and accepting their terms. The public search answers without one and gives price, size, chain and the leaflet's dates, which is all the tool needs. The risk is the one handle-mcp already takes with the stores' private APIs: it can change or close any day. A location would add personal data to the config for little gain, since local-only offers are rare.

## Consequences

- A chain is not a store (no cart, no delivery), so the search lives outside `STORES` and the store protocol.
- The search also answers with chains in Norway and Sweden, in their own currency. Every offer is kept only when its chain is on `/dealers?country_id=DK` and its price is in kroner, so the tool reads every page of `/dealers` (the first page alone leaves out Netto, Lidl and REMA 1000) and asks for three times the limit.
- Named chains go to the search as `dealer_ids`, so the ranking is among them.
- eTilbudsavis has no public link to one offer or leaflet page. The answer links the search on etilbudsavis.dk instead.
- Offers valid today and those starting within 7 days are returned, each with `valid_from` and `valid_until`.
- If Tjek closes the public search, the answer is a key from Tjek or removing the tool, not a workaround.
