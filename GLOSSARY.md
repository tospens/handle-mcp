# handle-mcp

Lets an AI agent find groceries and fill a cart at Danish grocery shops, while the human always orders and pays.

## Shops and offers

**Store**:
A grocery shop where handle-mcp can fill a cart: nemlig.com, BilkaToGo or REMA 1000.
_Avoid_: Shop, butik (in code and docs), dealer

**Chain**:
A grocery retailer that publishes a leaflet on eTilbudsavis, such as Netto, Lidl or føtex. A chain can also be a store (REMA 1000).
_Avoid_: Dealer, store, brand

**Leaflet offer**:
An offer from a chain's weekly leaflet, found through eTilbudsavis, valid in the chain's physical shops for a stated period.
_Avoid_: Tilbud (alone), deal, store offer

**Store offer**:
An offer a store shows in its own webshop, which can go straight into its cart.
_Avoid_: Leaflet offer, campaign

## Buying

**Cart**:
The products and quantities handle-mcp prepares in one store for the human to check and pay. At REMA 1000 the cart is the REMA list named "handle-mcp".
_Avoid_: Basket, shopping list, order
