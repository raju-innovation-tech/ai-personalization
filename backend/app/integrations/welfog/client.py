"""HTTP client for the engine's own API (so the sync uses exactly the validated public endpoints)."""
from __future__ import annotations

import os
import time

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


class EngineError(RuntimeError):
    pass


class EngineClient:
    def __init__(self, base_url: str, email: str | None = None, password: str | None = None, *,
                 timeout: float = 60.0, retries: int = 5, sleep=time.sleep, transport=None):
        self.base_url = base_url.rstrip("/")
        self.email, self.password = email, password
        self.retries, self._sleep = retries, sleep
        self._token: str | None = None
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    # -------------------------------------------------------------------- plumbing
    def _login(self) -> None:
        if not (self.email and self.password):
            raise EngineError("AI_ENGINE_EMAIL / AI_ENGINE_PASSWORD are required for this call (admin login)")
        response = self._http.post(f"{self.base_url}/auth/login", json={"email": self.email, "password": self.password})
        if response.status_code != 200:
            raise EngineError(f"engine login failed: HTTP {response.status_code}")
        self._token = response.json()["data"]["access_token"]

    def _send(self, method: str, path: str, body: dict, *, auth: bool) -> httpx.Response:
        relogged = False
        for attempt in range(self.retries + 1):
            headers = {}
            storefront_key = os.environ.get("STOREFRONT_API_KEY")
            if storefront_key:
                headers["X-API-Key"] = storefront_key
            if auth:
                if self._token is None:
                    self._login()
                headers["Authorization"] = f"Bearer {self._token}"
            try:
                response = self._http.request(method, f"{self.base_url}{path}", json=body, headers=headers)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                self._sleep(min(2 ** attempt, 30))
                continue
            if response.status_code == 401 and auth and not relogged:
                self._token, relogged = None, True
                continue
            if response.status_code in RETRY_STATUS and attempt < self.retries:
                self._sleep(min(2 ** attempt, 30))
                continue
            return response
        raise EngineError("unreachable")

    # ------------------------------------------------------------------- endpoints
    def post_events(self, events: list[dict]) -> tuple[int, int, int]:
        """-> (accepted, duplicates, rejected). A rejected batch is retried event by event."""
        response = self._send("POST", "/events/batch", {"events": events}, auth=False)
        if response.status_code == 201:
            data = response.json()["data"]
            return data["accepted"], data["duplicates"], data["rejected"]
        if response.status_code == 422 and len(events) > 1:
            totals = [0, 0, 0]
            for event in events:
                a, d, r = self.post_events([event])
                totals[0] += a; totals[1] += d; totals[2] += r
            return tuple(totals)  # type: ignore[return-value]
        if response.status_code == 422:
            return 0, 0, 1
        raise EngineError(f"POST /events/batch failed: HTTP {response.status_code} {response.text[:300]}")

    def upsert_products(self, products: list[dict]) -> tuple[int, int, int]:
        """-> (created, updated, rejected). A rejected batch is retried product by product."""
        response = self._send("POST", "/products/bulk", {"products": products}, auth=True)
        if response.status_code == 200:
            data = response.json()["data"]
            return data["created"], data["updated"], 0
        if response.status_code == 422 and len(products) > 1:
            totals = [0, 0, 0]
            for product in products:
                c, u, r = self.upsert_products([product])
                totals[0] += c; totals[1] += u; totals[2] += r
            return tuple(totals)  # type: ignore[return-value]
        if response.status_code == 422:
            return 0, 0, 1
        raise EngineError(f"POST /products/bulk failed: HTTP {response.status_code} {response.text[:300]}")
