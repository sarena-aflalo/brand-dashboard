"""
ShopMy API module.

API base: https://api.shopmy.us/v1
Auth:     Authorization: Bearer {SHOPMY_API_KEY}
Docs:     https://docs.shopmy.us/reference/fetch-order-report

Primary endpoint: POST /v1/Partners/OrderReport
  - Returns raw order rows for the current month
  - Aggregated here by creator into [{name, handle, revenue, orders, commission}]

Required env vars:
  SHOPMY_API_KEY   — Developer key from Account Settings > Tokens > Developer Key
  SHOPMY_DOMAIN    — Brand's registered domain in ShopMy (e.g. "aflalo.com")
"""

import os
import time
import httpx
from datetime import datetime, timezone

BASE_URL = "https://api.shopmy.us/v1"
CACHE_TTL = 1800  # 30 minutes

_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value):
    _cache[key] = (time.time(), value)


def _headers() -> dict:
    key = os.getenv("SHOPMY_API_KEY", "")
    if not key:
        raise ValueError("SHOPMY_API_KEY not set")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _month_range() -> tuple[str, str]:
    """Return (start, end) for the current calendar month as 'YYYY-MM-DD HH:mm:ss' UTC."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return (
        start.strftime("%Y-%m-%d %H:%M:%S"),
        now.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _extract_orders(body) -> list[dict]:
    """Normalise the response body — ShopMy returns either a bare list or a wrapped object."""
    if isinstance(body, list):
        return body
    for key in ("data", "orders", "results"):
        if key in body and isinstance(body[key], list):
            return body[key]
    return []


async def get_creator_performance(client: httpx.AsyncClient) -> list[dict]:
    """
    Return creator performance for the current month, sorted by revenue desc.
    Shape: [{name, handle, revenue, orders, commission}]
    """
    cached = _cache_get("creators")
    if cached is not None:
        return cached

    headers = _headers()
    domain = os.getenv("SHOPMY_DOMAIN", "")
    if not domain:
        raise ValueError("SHOPMY_DOMAIN not set")

    start, end = _month_range()

    # Paginate through all orders (max 500 per page)
    all_orders: list[dict] = []
    page = 0
    while True:
        resp = await client.post(
            f"{BASE_URL}/Partners/OrderReport",
            headers=headers,
            json={
                "domain": domain,
                "transactionStartDate": start,
                "transactionEndDate": end,
                "limit": 500,
                "page": page,
            },
        )
        print(f"[shopmy] OrderReport page={page} status={resp.status_code}", flush=True)
        if resp.status_code != 200:
            print(f"[shopmy] error: {resp.text[:300]}", flush=True)
        resp.raise_for_status()
        orders = _extract_orders(resp.json())
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < 500:
            break
        page += 1

    print(f"[shopmy] total orders fetched: {len(all_orders)}", flush=True)

    # Aggregate by creator
    by_creator: dict[str, dict] = {}
    for order in all_orders:
        name = order.get("Creator Name") or "Unknown"
        profile_url = order.get("Creator ShopMy", "")
        # Derive @handle from profile URL e.g. https://shopmy.us/username
        handle = ("@" + profile_url.rstrip("/").split("/")[-1]) if profile_url else ""

        revenue    = float(order.get("Order Amount USD")     or 0)
        commission = float(order.get("Commission Amount USD") or 0)

        if name not in by_creator:
            by_creator[name] = {
                "name":       name,
                "handle":     handle,
                "revenue":    0.0,
                "orders":     0,
                "commission": 0.0,
            }
        by_creator[name]["revenue"]    += revenue
        if revenue > 0:
            by_creator[name]["orders"] += 1
        by_creator[name]["commission"] += commission

    results = sorted(by_creator.values(), key=lambda x: x["revenue"], reverse=True)
    for r in results:
        r["revenue"]         = round(r["revenue"],    2)
        r["commission"]      = round(r["commission"], 2)
        r["commission_rate"] = round(r["commission"] / r["revenue"] * 100, 1) if r["revenue"] else 0.0

    if results:
        _cache_set("creators", results)
    return results


async def get_influencer_revenue(client: httpx.AsyncClient) -> float:
    """Total influencer revenue this month."""
    creators = await get_creator_performance(client)
    return round(sum(c["revenue"] for c in creators), 2)
