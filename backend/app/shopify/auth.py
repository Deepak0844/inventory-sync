"""Access tokens for the Shopify Admin API (client credentials grant).

The token lasts 24 hours, so it is requested again when it is close to expiring
and never stored. Not responsible for using the token (`app.shopify.client`).
"""

import httpx

from app.core.clock import Clock
from app.shopify.client import ShopifyError

SAFETY_MARGIN_S = 60.0


class ClientCredentialsToken:
    """Fetches and caches one shop's access token."""

    def __init__(
        self, shop: str, client_id: str, client_secret: str, transport: httpx.BaseTransport,
        clock: Clock,
    ) -> None:
        self._http = httpx.Client(base_url=f"https://{shop}", transport=transport)
        self._body = {"client_id": client_id, "client_secret": client_secret,
                      "grant_type": "client_credentials"}
        self._clock = clock
        self._token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        """Return a valid token, requesting a new one if needed.

        Raises:
            ShopifyError: if Shopify rejects the request or cannot be reached. The
                message never includes the client secret or the response body.
        """
        if self._clock.now() >= self._expires_at - SAFETY_MARGIN_S:
            try:
                response = self._http.post("/admin/oauth/access_token", json=self._body)
            except httpx.TransportError as exc:
                raise ShopifyError("could not reach Shopify for a token") from exc
            if response.status_code != 200:
                raise ShopifyError(f"Shopify refused the token request ({response.status_code})")
            data = response.json()
            self._token = data["access_token"]
            self._expires_at = self._clock.now() + float(data.get("expires_in", 86400))
        return self._token
