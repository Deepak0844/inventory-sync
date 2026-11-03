"""Reading the shop's Variants so mappings can refer to them by SKU.

Needs only the `read_products` scope. Not responsible for storing them.
"""

from dataclasses import dataclass
from typing import Protocol

from app.shopify.client import ShopifyClient

_QUERY = """
query($after: String) {
  productVariants(first: 100, after: $after) {
    nodes { id sku displayName }
    pageInfo { hasNextPage endCursor }
  }
}
"""


@dataclass(frozen=True)
class ShopVariant:
    """A Shopify Variant: its GID, SKU and display title."""

    id: str
    sku: str
    title: str


class VariantSource(Protocol):
    """Where the worker gets the shop's Variants from."""

    def all_variants(self) -> list[ShopVariant]:
        """Return every Variant that has a SKU."""
        ...


class ShopifyVariantReader:
    """Pages through every Variant in the shop."""

    def __init__(self, client: ShopifyClient) -> None:
        self._client = client

    def all_variants(self) -> list[ShopVariant]:
        """Return every Variant that has a SKU (the CSV import maps by SKU).

        Raises:
            ShopifyError: from the client, after its retries.
        """
        variants: list[ShopVariant] = []
        after: str | None = None
        while True:
            page = self._client.graphql(_QUERY, {"after": after})["productVariants"]
            variants += [ShopVariant(n["id"], n["sku"], n["displayName"])
                         for n in page["nodes"] if n["sku"]]
            if not page["pageInfo"]["hasNextPage"]:
                return variants
            after = page["pageInfo"]["endCursor"]
