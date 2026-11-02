# Inventory Sync

Keeps a dropshipping Shopify store honest about availability. It watches the Suppliers the store buys from and marks items Sold Out in Shopify when the Suppliers no longer have them.

## Language

**Supplier**:
A business the store buys items from after a customer orders. The store only lists Suppliers' items and holds no stock itself.
_Avoid_: Provider, vendor, seller

**Stock Source**:
How the system learns a Supplier's availability: by scraping the Supplier's site or by reading a feed the Supplier provides.
_Avoid_: Integration, connector

**Listing**:
A Supplier's page or row for one purchasable item, such as a product URL.
_Avoid_: Supplier product, provider item

**Variant**:
One purchasable option of a Shopify product (for example size M, colour red). A product with no options has a single Variant.
_Avoid_: SKU, option

**Login Code**:
The one-time code a Supplier sends during 2FA. It reaches the system either pasted by the store owner in the dashboard or read from the dedicated mailbox, whichever arrives first.
_Avoid_: OTP, token, verification code

**Mapping**:
The link between a Variant and one or more Listings, with a priority order among Listings.
_Avoid_: Link, binding

**Stock Status**:
What the system believes about a Listing: In Stock, Out of Stock, or Unknown. Unknown covers any failed check and never changes Shopify.
_Avoid_: Availability, in-stock flag

**Sold Out**:
The state of a Variant when every Listing mapped to it is Out of Stock. The system shows it in Shopify by setting inventory to 0.
_Avoid_: Disabled, hidden

**Restore**:
Returning a Sold Out Variant to available when any mapped Listing is In Stock again, with a default quantity.
_Avoid_: Re-enable, relist

**Stale**:
A Variant whose Stock Status is Unknown or whose last successful check is older than twice its check interval. Orders containing a Stale Variant are flagged "verify with Supplier".
_Avoid_: Outdated, unchecked

**Pending Approval**:
A batch of Stock Status changes held back because too many of a Supplier's Listings flipped to Out of Stock at once. It waits for the store owner's decision.
_Avoid_: Quarantine, blocked

**Listing Removed**:
A Listing whose page no longer exists (404 or redirect). Counts as Out of Stock after confirmation and is flagged for review.
_Avoid_: Dead link, broken URL
