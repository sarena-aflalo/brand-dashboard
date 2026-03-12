"""
Meta Graph API module.

API base: https://graph.facebook.com/v19.0
Auth:     access_token query param (long-lived token)
Endpoint: GET /act_{ad_account_id}/insights

Fetches all YTD ads at the ad level, deduplicates by creative ID,
then returns top 10 by revenue and bottom 10 (spend > 0, revenue = 0) by CTR.
"""

import os
import time
import json
import httpx
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, unquote
from datetime import datetime, timezone

BASE_URL = "https://graph.facebook.com/v19.0"
CACHE_TTL = 1800  # 30 minutes

_cache: dict[str, tuple[float, object]] = {}

PURCHASE_ACTION_TYPES = {
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
}


def _extract_best_url(thumbnail_url: str) -> str:
    """
    - Video ads wrap the real image in a url= query param — decode it.
    - Image ads: return as-is (stripping params breaks the signed CDN URL).
    """
    try:
        params = parse_qs(urlparse(thumbnail_url).query, keep_blank_values=True)
        if "url" in params:
            return unquote(params["url"][0])
        return thumbnail_url
    except Exception:
        return thumbnail_url


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value):
    _cache[key] = (time.time(), value)


def _base_params() -> dict:
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("META_ACCESS_TOKEN not set")
    return {"access_token": token}


def _ad_account_id() -> str:
    account_id = os.getenv("META_AD_ACCOUNT_ID", "")
    if not account_id:
        raise ValueError("META_AD_ACCOUNT_ID not set")
    return account_id


def _extract_action_value(rows: list, action_types: set) -> float:
    for row in rows:
        if row.get("action_type") in action_types:
            return float(row.get("value") or 0)
    return 0.0


async def _fetch_all_creatives(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch all YTD ad insights, paginate, deduplicate by creative ID.
    Returns a flat list of creative-level dicts.
    """
    cached = _cache_get("meta_all")
    if cached is not None:
        return cached

    params = _base_params()
    account_id = _ad_account_id()

    params.update({
        "fields": "ad_id,ad_name,spend,impressions,clicks,action_values,actions",
        "level": "ad",
        "date_preset": "this_year",
        "limit": "500",
    })

    # Paginate through all results
    raw_rows: list[dict] = []
    url = f"{BASE_URL}/act_{account_id}/insights"

    while url:
        resp = await client.get(url, params=params)
        print(f"[meta] insights status={resp.status_code}", flush=True)
        if resp.status_code != 200:
            print(f"[meta] error: {resp.text[:300]}", flush=True)
        resp.raise_for_status()
        body = resp.json()
        raw_rows.extend(body.get("data", []))
        url = body.get("paging", {}).get("next")
        params = {}  # next URL already includes all params

    print(f"[meta] total ad rows fetched: {len(raw_rows)}", flush=True)

    # Fetch creative IDs per ad, then batch-fetch 1080px thumbnails
    thumbnails: dict[str, str] = {}
    creative_to_ad_ids: dict[str, list[str]] = {}
    ad_created_times: dict[str, str] = {}
    try:
        ad_params = _base_params()
        ad_params.update({"fields": "id,created_time,creative{id}", "limit": "500"})
        ads_url = f"{BASE_URL}/act_{account_id}/ads"

        while ads_url:
            r = await client.get(ads_url, params=ad_params)
            if r.status_code != 200:
                print(f"[meta] ads fetch failed {r.status_code}: {r.text[:200]}", flush=True)
                break
            body = r.json()
            for ad in body.get("data", []):
                ad_id       = ad["id"]
                creative    = ad.get("creative", {})
                creative_id = creative.get("id")
                if creative_id:
                    creative_to_ad_ids.setdefault(creative_id, []).append(ad_id)
                if ad.get("created_time"):
                    ad_created_times[ad_id] = ad["created_time"]
            ads_url   = body.get("paging", {}).get("next")
            ad_params = {}

        # Batch-fetch 1080px thumbnails in chunks of 50
        creative_ids = list(creative_to_ad_ids.keys())
        CHUNK = 50
        for i in range(0, len(creative_ids), CHUNK):
            chunk = creative_ids[i : i + CHUNK]
            batch = [
                {"method": "GET", "relative_url": f"{cid}?fields=thumbnail_url,picture&thumbnail_width=1080&thumbnail_height=1080"}
                for cid in chunk
            ]
            batch_params = _base_params()
            batch_params["batch"] = json.dumps(batch)
            resp = await client.post(BASE_URL, data=batch_params)
            print(f"[meta] batch chunk {i//CHUNK+1} status={resp.status_code}", flush=True)
            if resp.status_code != 200:
                print(f"[meta] batch error: {resp.text[:200]}", flush=True)
                continue
            for j, item in enumerate(resp.json()):
                if not item or item.get("code") != 200:
                    print(f"[meta] batch item {i+j} failed code={item.get('code') if item else None}: {str(item)[:200]}", flush=True)
                    continue
                try:
                    body = json.loads(item["body"])
                    raw_thumb = body.get("thumbnail_url", "") or body.get("picture", "")
                    if raw_thumb:
                        best = _extract_best_url(raw_thumb)
                        cid = chunk[j]
                        thumbnails[cid] = best  # keyed by creative_id
                        for aid in creative_to_ad_ids.get(cid, []):
                            thumbnails[aid] = best  # also keyed by ad_id as fallback
                except Exception:
                    pass

        print(f"[meta] images resolved: {len(thumbnails)}", flush=True)
    except Exception as e:
        print(f"[meta] image fetch error (non-fatal): {e}", flush=True)

    # Build reverse mapping: ad_id → creative_id
    ad_to_creative: dict[str, str] = {}
    for cid, ad_ids in creative_to_ad_ids.items():
        for aid in ad_ids:
            ad_to_creative[aid] = cid

    # Deduplicate by creative_id — sum spend/impressions/clicks/revenue/orders
    by_creative: dict[str, dict] = {}
    for row in raw_rows:
        ad_id         = row.get("ad_id", "unknown")
        creative_id   = ad_to_creative.get(ad_id, ad_id)
        creative_name = row.get("ad_name", "Unknown Ad")
        thumbnail_url = thumbnails.get(creative_id, "")

        spend       = float(row.get("spend", 0) or 0)
        impressions = int(row.get("impressions", 0) or 0)
        clicks      = int(row.get("clicks", 0) or 0)
        revenue     = _extract_action_value(row.get("action_values", []), PURCHASE_ACTION_TYPES)
        orders      = int(_extract_action_value(row.get("actions", []), PURCHASE_ACTION_TYPES))

        if creative_id not in by_creative:
            by_creative[creative_id] = {
                "creative_id":    creative_id,
                "creative_name":  creative_name,
                "thumbnail_url":  thumbnail_url,
                "created_time":   ad_created_times.get(ad_id, ""),
                "spend":          0.0,
                "impressions":    0,
                "clicks":         0,
                "revenue":        0.0,
                "orders":         0,
            }
        by_creative[creative_id]["spend"]       += spend
        by_creative[creative_id]["impressions"] += impressions
        by_creative[creative_id]["clicks"]      += clicks
        by_creative[creative_id]["revenue"]     += revenue
        by_creative[creative_id]["orders"]      += orders

    results = []
    for c in by_creative.values():
        spend  = round(c["spend"], 2)
        rev    = round(c["revenue"], 2)
        impr   = c["impressions"]
        clks   = c["clicks"]
        roas   = round(rev / spend, 2) if spend else 0.0
        ctr    = round(clks / impr * 100, 2) if impr else 0.0
        results.append({
            "creative_id":   c["creative_id"],
            "creative_name": c["creative_name"],
            "thumbnail_url": c["thumbnail_url"],
            "created_time":  c["created_time"],
            "spend":         spend,
            "revenue":       rev,
            "roas":          roas,
            "impressions":   impr,
            "clicks":        clks,
            "ctr":           ctr,
            "orders":        c["orders"],
        })

    if results:
        _cache_set("meta_all", results)
    return results


def _ad_age_days(created_time: str) -> float:
    """Return how many days ago an ad was created. Returns 999 if unknown."""
    if not created_time:
        return 999.0
    try:
        created = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created).total_seconds() / 86400
    except Exception:
        return 999.0


async def get_creative_performance(client: httpx.AsyncClient) -> dict:
    """
    Return top 10 ads by revenue and bottom 10 (spend > 0, no sales, live >= 7 days) by CTR.
    Shape: {
        "top":    [{creative_name, thumbnail_url, spend, revenue, roas, orders, ctr}],
        "bottom": [{creative_name, thumbnail_url, spend, impressions, clicks, ctr}],
    }
    """
    all_creatives = await _fetch_all_creatives(client)

    top = sorted(
        [c for c in all_creatives if c["revenue"] > 0],
        key=lambda x: x["revenue"],
        reverse=True,
    )[:10]

    bottom = sorted(
        [c for c in all_creatives
         if c["spend"] > 0 and c["revenue"] == 0
         and _ad_age_days(c["created_time"]) >= 7],
        key=lambda x: x["ctr"],
    )[:10]

    return {"top": top, "bottom": bottom}


async def get_paid_revenue(client: httpx.AsyncClient) -> float:
    """Total paid revenue YTD."""
    all_creatives = await _fetch_all_creatives(client)
    return round(sum(c["revenue"] for c in all_creatives), 2)
