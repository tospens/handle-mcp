# eTilbudsavis fixtures

Real answers from `https://api.etilbudsavis.dk/v2`, captured 2026-11-17 without a key or a login
(docs/adr/0016). Nothing personal is in them. Fields the code does not read are removed to keep
the files small; the values that are left are as the API sent them.

- `dealers_offset_{0,100,200,300}.json`: `/dealers?country_id=DK&limit=100&offset=…`, every
  Danish chain (306). Netto, Lidl and REMA 1000 are not on the first page.
- `search_kaffe.json`: `/offers/search?query=kaffe&country_id=DK&limit=60`. It also has chains
  from Norway and Sweden (prices in NOK and SEK), which the tool must leave out.
- `search_kaffe_chains.json`: the same with `dealer_ids` for Netto, Lidl, føtex, REMA 1000,
  Bilka and SuperBrugsen.

Offers are valid from 2026-09-12 to 2026-12-31; tests pass `today=2026-11-17`.
