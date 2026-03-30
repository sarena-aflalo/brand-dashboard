"""
Klaviyo API module.

API base: https://a.klaviyo.com/api
Auth: Authorization: Klaviyo-API-Key {key}
Revision header required: revision: 2024-02-15

Endpoints used:
  GET /campaigns?filter=equals(messages.channel,'email')&include=campaign-messages
  GET /campaigns/{id}/campaign-send-job  (send stats)
  GET /campaign-values-reports           (revenue via metric aggregation)
  GET /flows                             (all flows)
  GET /flow-values-reports               (flow revenue/sends)
  GET /lists                             (subscriber lists)
  GET /lists/{id}/profiles               (list members for source breakdown)
"""

import os
import time
import json
import asyncio
import httpx
from pathlib import Path
from datetime import datetime, timezone

BASE_URL = "https://a.klaviyo.com/api"
REVISION = "2024-02-15"
CACHE_TTL = 7200  # seconds (2 hours)

_cache: dict[str, tuple[float, object]] = {}
_fetch_lock = asyncio.Lock()   # prevents concurrent campaign report calls on cold start
_flows_lock = asyncio.Lock()   # prevents concurrent flow report calls on cold start
_rate_lock = asyncio.Lock()   # ensures minimum 1.5s gap between any two Klaviyo POST calls

# Persistent disk cache — survives backend restarts so we don't re-hit Klaviyo on every reload
_DISK_CACHE_PATH = Path(__file__).parent / ".cache" / "klaviyo_cache.json"


def _disk_cache_load():
    """Load persisted cache entries into memory on startup."""
    try:
        if _DISK_CACHE_PATH.exists():
            data = json.loads(_DISK_CACHE_PATH.read_text())
            now = time.time()
            for key, (ts, val) in data.items():
                if now - ts < CACHE_TTL:
                    _cache[key] = (ts, val)
            print(f"[klaviyo] loaded {len(_cache)} cache entries from disk", flush=True)
    except Exception as e:
        print(f"[klaviyo] disk cache load failed (non-fatal): {e}", flush=True)


def _disk_cache_save():
    """Persist current in-memory cache to disk."""
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DISK_CACHE_PATH.write_text(json.dumps(_cache))
    except Exception as e:
        print(f"[klaviyo] disk cache save failed (non-fatal): {e}", flush=True)


_disk_cache_load()
_last_post_time: float = 0.0


async def _rate_limited_post(client: httpx.AsyncClient, url: str, **kwargs):
    """Wrapper for POST calls that enforces a minimum gap and retries on 429."""
    global _last_post_time
    async with _rate_lock:
        wait = 2.0 - (time.time() - _last_post_time)
        if wait > 0:
            await asyncio.sleep(wait)
        resp = await client.post(url, **kwargs)
        _last_post_time = time.time()

        if resp.status_code == 429:
            retry_after = 15
            try:
                detail = resp.json().get("errors", [{}])[0].get("detail", "")
                import re
                m = re.search(r"(\d+) seconds", detail)
                if m:
                    retry_after = min(int(m.group(1)) + 2, 60)  # cap at 60s — never sleep for hours
            except Exception:
                pass
            print(f"[klaviyo] 429 throttled, retrying in {retry_after}s", flush=True)
            await asyncio.sleep(retry_after)
            resp = await client.post(url, **kwargs)
            _last_post_time = time.time()

    return resp


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, value):
    _cache[key] = (time.time(), value)
    _disk_cache_save()


def _headers() -> dict:
    key = os.getenv("KLAVIYO_API_KEY", "")
    if not key:
        raise ValueError("KLAVIYO_API_KEY not set")
    return {
        "Authorization": f"Klaviyo-API-Key {key}",
        "revision": REVISION,
        "Accept": "application/json",
    }


def _month_range() -> tuple[str, str]:
    """Return ISO8601 start/end for the current calendar month (UTC)."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return start.isoformat(), now.isoformat()


def _year_range() -> tuple[str, str]:
    """Return ISO8601 start/end for the current calendar year (UTC)."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    return start.isoformat(), now.isoformat()


async def _get_metric_ids(client: httpx.AsyncClient, headers: dict) -> dict:
    """
    Fetch all metric IDs needed across the module in one API call.
    Returns dict with keys: placed_order_id, subscribe_id, unsubscribe_id.
    Results are cached individually so each can be used independently.
    """
    # Return early if all IDs already cached
    placed = _cache_get("metric_placed_order_id")
    sub    = _cache_get("metric_subscribe_id")
    unsub  = _cache_get("metric_unsubscribe_id")
    if placed is not None and sub is not None and unsub is not None:
        return {"placed_order_id": placed, "subscribe_id": sub, "unsubscribe_id": unsub}

    resp = await client.get(f"{BASE_URL}/metrics", headers=headers)
    if resp.status_code != 200:
        return {"placed_order_id": placed, "subscribe_id": sub, "unsubscribe_id": unsub}

    for m in resp.json().get("data", []):
        name = m.get("attributes", {}).get("name", "").lower()
        mid  = m["id"]
        if "placed order" in name and placed is None:
            placed = mid
            _cache_set("metric_placed_order_id", mid)
            print(f"[klaviyo] found conversion metric: {mid} ({m['attributes']['name']})", flush=True)
        elif "subscribed to list" in name and sub is None:
            sub = mid
            _cache_set("metric_subscribe_id", mid)
            print(f"[klaviyo] found subscribe metric: {mid}", flush=True)
        elif "unsubscribed from list" in name and unsub is None:
            unsub = mid
            _cache_set("metric_unsubscribe_id", mid)
            print(f"[klaviyo] found unsubscribe metric: {mid}", flush=True)

    if not placed:
        print("[klaviyo] WARNING: 'Placed Order' metric not found", flush=True)
    return {"placed_order_id": placed, "subscribe_id": sub, "unsubscribe_id": unsub}


async def _get_placed_order_metric_id(client: httpx.AsyncClient, headers: dict) -> str | None:
    """Find the metric ID for 'Placed Order'. Fetches all metric IDs in one call and caches them."""
    ids = await _get_metric_ids(client, headers)
    return ids["placed_order_id"]


async def get_campaign_performance(client: httpx.AsyncClient) -> list[dict]:
    """
    Return campaign performance for the current month.
    Shape: [{subject, preview_text, send_date, revenue, sends, per_send}]
    """
    cached = _cache_get("campaigns")
    if cached is not None:
        return cached
    # Lock prevents concurrent cold-start fetches from both hitting Klaviyo simultaneously
    async with _fetch_lock:
        cached = _cache_get("campaigns")
        if cached is not None:
            return cached
        return await _fetch_campaign_performance(client)


async def _fetch_campaign_performance(client: httpx.AsyncClient) -> dict:
    """Inner fetch — called only while _fetch_lock is held."""
    headers = _headers()
    start, end = _month_range()

    # 1. Fetch sent campaigns this month (status=Sent ensures drafts/scheduled are excluded)
    campaigns_resp = await client.get(
        f"{BASE_URL}/campaigns",
        headers=headers,
        params={
            "filter": (
                f"and(equals(messages.channel,'email'),"
                f"equals(status,'Sent'),"
                f"greater-or-equal(scheduled_at,{start}),"
                f"less-or-equal(scheduled_at,{end}))"
            ),
            "include": "campaign-messages",
            "fields[campaign]": "name,scheduled_at,send_time,status",
            "fields[campaign-message]": "label,content",
        },
    )
    campaigns_resp.raise_for_status()
    campaigns_data = campaigns_resp.json()

    campaign_list = campaigns_data.get("data", [])
    included = campaigns_data.get("included", [])

    # Build subject + preview_text + message_id lookup from included campaign-messages
    subject_by_campaign: dict[str, str] = {}
    preview_by_campaign: dict[str, str] = {}
    message_id_by_campaign: dict[str, str] = {}
    for item in included:
        if item.get("type") == "campaign-message":
            cid = (
                item.get("relationships", {})
                .get("campaign", {})
                .get("data", {})
                .get("id", "")
            )
            content = item.get("attributes", {}).get("content", {})
            msg_id = item.get("id", "")
            print(f"[klaviyo] campaign-message item id={msg_id} campaign_id={cid}", flush=True)
            if cid:
                subject_by_campaign[cid] = content.get("subject", "")
                preview_by_campaign[cid] = content.get("preview_text", "")
                message_id_by_campaign[cid] = msg_id

    if not campaign_list:
        return []

    # 2. Find "Placed Order" metric ID — required by campaign-values-reports
    conversion_metric_id = await _get_placed_order_metric_id(client, headers)

    # 3. Fetch campaign value reports for revenue + sends
    campaign_ids = [c["id"] for c in campaign_list]

    report_body: dict = {
        "data": {
            "type": "campaign-values-report",
            "attributes": {
                "timeframe": {"start": start, "end": end},
                "statistics": [
                    "recipients",
                    "conversion_value",
                    "open_rate",
                    "click_rate",
                    "conversion_rate",
                    "unsubscribe_rate",
                ],
            },
        }
    }
    if conversion_metric_id:
        report_body["data"]["attributes"]["conversion_metric_id"] = conversion_metric_id

    report_resp = await _rate_limited_post(
        client,
        f"{BASE_URL}/campaign-values-reports",
        headers=headers,
        json=report_body,
    )
    print(f"[klaviyo] campaign-values-reports status: {report_resp.status_code}")
    if report_resp.status_code != 200:
        print(f"[klaviyo] campaign-values-reports error: {report_resp.text}")

    stats_by_id: dict[str, dict] = {}
    if report_resp.status_code == 200:
        resp_json = report_resp.json()
        results_raw = resp_json.get("data", {}).get("attributes", {}).get("results", [])
        print(f"[klaviyo] campaign-values-reports rows: {len(results_raw)}", flush=True)
        if results_raw:
            print(f"[klaviyo] first result sample: {results_raw[0]}", flush=True)
        for row in results_raw:
            cid = row.get("groupings", {}).get("campaign_id", "")
            s = row.get("statistics", {})
            if cid in stats_by_id:
                stats_by_id[cid]["recipients"] = (stats_by_id[cid].get("recipients") or 0) + (s.get("recipients") or 0)
                stats_by_id[cid]["conversion_value"] = (stats_by_id[cid].get("conversion_value") or 0) + (s.get("conversion_value") or 0)
                # For rates, keep the value from the first row (they shouldn't differ across message splits)
                if "open_rate" not in stats_by_id[cid]:
                    stats_by_id[cid]["open_rate"] = s.get("open_rate")
                if "click_rate" not in stats_by_id[cid]:
                    stats_by_id[cid]["click_rate"] = s.get("click_rate")
                if "conversion_rate" not in stats_by_id[cid]:
                    stats_by_id[cid]["conversion_rate"] = s.get("conversion_rate")
                if "unsubscribe_rate" not in stats_by_id[cid]:
                    stats_by_id[cid]["unsubscribe_rate"] = s.get("unsubscribe_rate")
            else:
                stats_by_id[cid] = {
                    "recipients": s.get("recipients") or 0,
                    "conversion_value": s.get("conversion_value") or 0,
                    "open_rate": s.get("open_rate"),
                    "click_rate": s.get("click_rate"),
                    "conversion_rate": s.get("conversion_rate"),
                    "unsubscribe_rate": s.get("unsubscribe_rate"),
                }
    else:
        print(f"[klaviyo] report failed {report_resp.status_code}: {report_resp.text}", flush=True)

    results = []
    for c in campaign_list:
        cid = c["id"]
        attrs = c.get("attributes", {})
        stats = stats_by_id.get(cid, {})
        sends = int(stats.get("recipients") or 0)
        revenue = float(stats.get("conversion_value", 0) or 0)
        per_send = round(revenue / sends, 4) if sends else 0.0
        results.append(
            {
                "id": cid,
                "subject": subject_by_campaign.get(cid, ""),
                "preview_text": preview_by_campaign.get(cid, ""),
                "send_date": attrs.get("send_time") or attrs.get("scheduled_at", ""),
                "revenue": revenue,
                "sends": sends,
                "per_send": per_send,
                "open_rate": stats.get("open_rate"),
                "ctr": stats.get("click_rate"),
                "cvr": stats.get("conversion_rate"),
                "unsubscribe_rate": stats.get("unsubscribe_rate"),
            }
        )

    # Small delay before YTD call to avoid hitting Klaviyo rate limits back-to-back
    await asyncio.sleep(1)

    # Fetch YTD averages and assign badges vs YTD average
    ytd = await _get_ytd_averages(client, headers, conversion_metric_id)

    if ytd["avg_per_send"] > 0:
        for r in results:
            ratio = r["per_send"] / ytd["avg_per_send"]
            if ratio >= 1.10:
                r["badge"] = "strong"
            elif ratio <= 0.90:
                r["badge"] = "weak"
            else:
                r["badge"] = "average"
    else:
        for r in results:
            r["badge"] = None

    # Sort by send date, most recent first
    results.sort(key=lambda x: x["send_date"] or "", reverse=True)

    payload = {"campaigns": results, "ytd": ytd}

    # Only cache if the values report succeeded (don't cache rate-limited zeros)
    if stats_by_id:
        _cache_set("campaigns", payload)
    return payload


async def _get_ytd_averages(client: httpx.AsyncClient, headers: dict, conversion_metric_id: str | None) -> dict:
    """Return YTD average revenue, sends, and $ per send across all sent campaigns."""
    cached = _cache_get("ytd")
    if cached is not None:
        return cached

    ytd_start, ytd_end = _year_range()

    report_body: dict = {
        "data": {
            "type": "campaign-values-report",
            "attributes": {
                "timeframe": {"start": ytd_start, "end": ytd_end},
                "statistics": ["recipients", "conversion_value", "open_rate", "click_rate", "conversion_rate", "unsubscribe_rate"],
            },
        }
    }
    if conversion_metric_id:
        report_body["data"]["attributes"]["conversion_metric_id"] = conversion_metric_id

    resp = await _rate_limited_post(
        client,
        f"{BASE_URL}/campaign-values-reports",
        headers=headers,
        json=report_body,
    )

    print(f"[klaviyo] ytd report status: {resp.status_code}", flush=True)
    if resp.status_code != 200:
        print(f"[klaviyo] ytd report error: {resp.text}", flush=True)

    total_revenue = 0.0
    total_sends = 0
    total_open_rate = 0.0
    total_click_rate = 0.0
    total_conversion_rate = 0.0
    campaign_ids_seen: set = set()
    # Track per-campaign rates to average correctly (one rate per campaign, not per message)
    campaign_rates: dict[str, dict] = {}

    if resp.status_code == 200:
        rows = resp.json().get("data", {}).get("attributes", {}).get("results", [])
        print(f"[klaviyo] ytd rows: {len(rows)}", flush=True)
        for row in rows:
            cid = row.get("groupings", {}).get("campaign_id", "")
            s = row.get("statistics", {})
            campaign_ids_seen.add(cid)
            total_revenue += float(s.get("conversion_value") or 0)
            total_sends += int(s.get("recipients") or 0)
            if cid not in campaign_rates:
                campaign_rates[cid] = {
                    "open_rate": s.get("open_rate"),
                    "click_rate": s.get("click_rate"),
                    "unsubscribe_rate": s.get("unsubscribe_rate"),
                    "conversion_rate": s.get("conversion_rate"),
                }
        print(f"[klaviyo] ytd totals: campaigns={len(campaign_ids_seen)} revenue={total_revenue} sends={total_sends}", flush=True)

    count = len(campaign_ids_seen)
    avg_revenue = round(total_revenue / count, 2) if count else 0.0
    avg_sends = round(total_sends / count) if count else 0
    avg_per_send = round(total_revenue / total_sends, 4) if total_sends else 0.0

    open_rates = [v["open_rate"] for v in campaign_rates.values() if v["open_rate"] is not None]
    click_rates = [v["click_rate"] for v in campaign_rates.values() if v["click_rate"] is not None]
    conv_rates = [v["conversion_rate"] for v in campaign_rates.values() if v["conversion_rate"] is not None]
    unsub_rates = [v["unsubscribe_rate"] for v in campaign_rates.values() if v.get("unsubscribe_rate") is not None]
    avg_open_rate = round(sum(open_rates) / len(open_rates), 6) if open_rates else None
    avg_click_rate = round(sum(click_rates) / len(click_rates), 6) if click_rates else None
    avg_conversion_rate = round(sum(conv_rates) / len(conv_rates), 6) if conv_rates else None
    avg_unsub_rate = round(sum(unsub_rates) / len(unsub_rates), 6) if unsub_rates else None

    result = {
        "campaign_count": count,
        "avg_revenue": avg_revenue,
        "avg_sends": avg_sends,
        "avg_per_send": avg_per_send,
        "avg_open_rate": avg_open_rate,
        "avg_ctr": avg_click_rate,
        "avg_cvr": avg_conversion_rate,
        "avg_unsub_rate": avg_unsub_rate,
    }
    if count:
        _cache_set("ytd", result)
    return result


async def get_send_time_analysis(client: httpx.AsyncClient) -> list[dict]:
    """
    Return all LTD campaigns with send_date and click_rate for send-time heatmap.
    Shape: [{send_date, ctr}]
    """
    cached = _cache_get("send_time_analysis")
    if cached is not None:
        return cached

    headers = _headers()
    now = datetime.now(timezone.utc)
    ltd_start = "2020-01-01T00:00:00Z"
    year_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ytd_start = ltd_start
    ytd_end = year_end
    campaigns_resp = await client.get(
        f"{BASE_URL}/campaigns",
        headers=headers,
        params={
            "filter": (
                f"and(equals(messages.channel,'email'),"
                f"equals(status,'Sent'),"
                f"greater-or-equal(scheduled_at,{ltd_start}),"
                f"less-or-equal(scheduled_at,{year_end}))"
            ),
            "fields[campaign]": "name,scheduled_at,send_time,status",
        },
    )
    campaigns_resp.raise_for_status()
    campaign_list = campaigns_resp.json().get("data", [])

    if not campaign_list:
        return []

    # Fetch click_rate for all campaigns via campaign-values-reports
    conversion_metric_id = await _get_placed_order_metric_id(client, headers)
    report_body: dict = {
        "data": {
            "type": "campaign-values-report",
            "attributes": {
                "timeframe": {"start": ytd_start, "end": ytd_end},
                "statistics": ["click_rate"],
            },
        }
    }
    if conversion_metric_id:
        report_body["data"]["attributes"]["conversion_metric_id"] = conversion_metric_id

    report_resp = await _rate_limited_post(
        client,
        f"{BASE_URL}/campaign-values-reports",
        headers=headers,
        json=report_body,
    )

    ctr_by_id: dict[str, float] = {}
    if report_resp.status_code == 200:
        rows = report_resp.json().get("data", {}).get("attributes", {}).get("results", [])
        for row in rows:
            cid = row.get("groupings", {}).get("campaign_id", "")
            cr = row.get("statistics", {}).get("click_rate")
            if cid and cr is not None and cid not in ctr_by_id:
                ctr_by_id[cid] = float(cr)
    else:
        print(f"[klaviyo] send_time report failed {report_resp.status_code}", flush=True)

    results = []
    for c in campaign_list:
        cid = c["id"]
        attrs = c.get("attributes", {})
        send_date = attrs.get("send_time") or attrs.get("scheduled_at", "")
        ctr = ctr_by_id.get(cid)
        if send_date and ctr is not None:
            results.append({"send_date": send_date, "ctr": ctr})

    if results:
        _cache_set("send_time_analysis", results)
    return results


FLOW_NAMES = {
    "abandoned_cart": "Abandoned Cart",
    "back_in_stock": "Back in Stock",
    "welcome_series": "Welcome Series",
}


async def get_flow_performance(client: httpx.AsyncClient) -> list[dict]:
    """
    Return revenue + sends for Abandoned Cart, Back in Stock, Welcome Series.
    Shape: [{name, revenue, sends, per_send}]

    We match flows by name substring (case-insensitive).
    """
    cached = _cache_get("flows")
    if cached is not None:
        return cached
    async with _flows_lock:
        cached = _cache_get("flows")
        if cached is not None:
            return cached
        return await _fetch_flow_performance(client)


async def _fetch_flow_performance(client: httpx.AsyncClient) -> list[dict]:
    """Inner fetch — called only while _flows_lock is held."""
    headers = _headers()
    start, end = _month_range()

    flows_resp = await client.get(
        f"{BASE_URL}/flows",
        headers=headers,
        params={"fields[flow]": "name,status"},
    )
    flows_resp.raise_for_status()
    all_flows = flows_resp.json().get("data", [])

    target_keywords = ["abandoned cart", "abandoned checkout", "back in stock"]
    matched: list[dict] = []
    for flow in all_flows:
        name = flow.get("attributes", {}).get("name", "").lower()
        for kw in target_keywords:
            if kw in name:
                matched.append(flow)
                break

    if not matched:
        # Return empty placeholders so the UI always renders
        return [
            {"id": None, "name": label, "revenue": 0.0, "sends": 0, "per_send": 0.0}
            for label in ["Abandoned Cart", "Abandoned Checkout", "Back in Stock", "Welcome Series"]
        ]

    flow_ids = [f["id"] for f in matched]
    conversion_metric_id = await _get_placed_order_metric_id(client, headers)

    report_body: dict = {
        "data": {
            "type": "flow-values-report",
            "attributes": {
                "timeframe": {"start": start, "end": end},
                "filter": f"contains-any(flow_id,[{','.join(repr(i) for i in flow_ids)}])",
                "statistics": ["recipients", "conversion_value"],
                "group_by": ["flow_id", "flow_message_id"],
            },
        }
    }
    if conversion_metric_id:
        report_body["data"]["attributes"]["conversion_metric_id"] = conversion_metric_id

    report_resp = await _rate_limited_post(
        client,
        f"{BASE_URL}/flow-values-reports",
        headers=headers,
        json=report_body,
    )
    print(f"[klaviyo] flow-values-reports status: {report_resp.status_code}", flush=True)
    if report_resp.status_code != 200:
        print(f"[klaviyo] flow-values-reports error: {report_resp.text}", flush=True)

    stats_by_id: dict[str, dict] = {}
    if report_resp.status_code == 200:
        for row in report_resp.json().get("data", {}).get("attributes", {}).get("results", []):
            fid = row.get("groupings", {}).get("flow_id", "")
            s = row.get("statistics", {})
            if fid in stats_by_id:
                stats_by_id[fid]["recipients"] = (stats_by_id[fid].get("recipients") or 0) + (s.get("recipients") or 0)
                stats_by_id[fid]["conversion_value"] = (stats_by_id[fid].get("conversion_value") or 0) + (s.get("conversion_value") or 0)
            else:
                stats_by_id[fid] = {"recipients": s.get("recipients") or 0, "conversion_value": s.get("conversion_value") or 0}
        print(f"[klaviyo] flow stats_by_id: {stats_by_id}", flush=True)

    results = []
    for f in matched:
        fid = f["id"]
        raw_name = f.get("attributes", {}).get("name", "")
        stats = stats_by_id.get(fid, {})
        sends = int(stats.get("recipients") or 0)
        revenue = float(stats.get("conversion_value", 0) or 0)
        per_send = round(revenue / sends, 4) if sends else 0.0
        results.append(
            {
                "id": fid,
                "name": raw_name,
                "revenue": revenue,
                "sends": sends,
                "per_send": per_send,
            }
        )

    if stats_by_id:
        _cache_set("flows", results)
    return results


async def get_subscriber_growth(client: httpx.AsyncClient) -> dict:
    """
    Return subscriber growth breakdown for the current month.
    Shape: {
      net_new, gross_adds, unsubscribes,
      goal: 1000,
      sources: {popup: int, waitlist: int, footer: int, other: int}
    }

    Klaviyo doesn't expose a single "source breakdown" endpoint out of the box.
    We use the /metrics endpoint to pull subscribe/unsubscribe events and
    group by $source property. This requires the metric IDs for those events.

    If the metric IDs can't be found, we fall back to list-level counts.
    """
    cached = _cache_get("subscribers")
    if cached is not None:
        return cached
    headers = _headers()
    start, end = _month_range()

    # Reuse cached metric IDs — avoids a separate /metrics call if already fetched
    metric_ids   = await _get_metric_ids(client, headers)
    subscribe_id   = metric_ids["subscribe_id"]
    unsubscribe_id = metric_ids["unsubscribe_id"]
    print(f"[klaviyo] subscriber metrics found: subscribe_id={subscribe_id} unsubscribe_id={unsubscribe_id}", flush=True)

    gross_adds = 0
    unsubscribes = 0
    sources: dict[str, int] = {"popup": 0, "waitlist": 0, "footer": 0, "other": 0}

    # NOTE: Klaviyo metric-aggregates does not support grouping by $source.
    # Source breakdown (popup/waitlist/footer) is not available via this API.
    # gross_adds comes from the total "Subscribed to List" count for the month.
    if subscribe_id:
        agg_resp = await _rate_limited_post(
            client,
            f"{BASE_URL}/metric-aggregates",
            headers=headers,
            json={
                "data": {
                    "type": "metric-aggregate",
                    "attributes": {
                        "metric_id": subscribe_id,
                        "measurements": ["count"],
                        "interval": "month",
                        "filter": f"and(greater-or-equal(datetime,{start}),less-than(datetime,{end}))",
                    },
                }
            },
        )
        print(f"[klaviyo] subscribe agg status: {agg_resp.status_code}", flush=True)
        if agg_resp.status_code != 200:
            print(f"[klaviyo] subscribe agg error: {agg_resp.text}", flush=True)
        if agg_resp.status_code == 200:
            for row in (
                agg_resp.json()
                .get("data", {})
                .get("attributes", {})
                .get("data", [])
            ):
                count = int(row.get("measurements", {}).get("count", [0])[0] or 0)
                gross_adds += count
            print(f"[klaviyo] gross_adds: {gross_adds}", flush=True)

    if unsubscribe_id:
        unsub_resp = await _rate_limited_post(
            client,
            f"{BASE_URL}/metric-aggregates",
            headers=headers,
            json={
                "data": {
                    "type": "metric-aggregate",
                    "attributes": {
                        "metric_id": unsubscribe_id,
                        "measurements": ["count"],
                        "interval": "month",
                        "filter": f"and(greater-or-equal(datetime,{start}),less-than(datetime,{end}))",
                    },
                }
            },
        )
        if unsub_resp.status_code == 200:
            data_rows = (
                unsub_resp.json()
                .get("data", {})
                .get("attributes", {})
                .get("data", [])
            )
            for row in data_rows:
                unsubscribes += int(
                    row.get("measurements", {}).get("count", [0])[0] or 0
                )

    total_subscribers = await _get_list_profile_count(client, headers, "Newsletter")

    result = {
        "gross_adds": gross_adds,
        "unsubscribes": unsubscribes,
        "net_new": gross_adds - unsubscribes,
        "goal": 500,
        "sources": sources,
        "total_subscribers": total_subscribers,
    }
    _cache_set("subscribers", result)
    return result


async def _get_list_profile_count(client: httpx.AsyncClient, headers: dict, list_name: str) -> int:
    """Find a list by name and return its profile count via the profiles relationship."""
    # Step 1: find the list ID
    resp = await client.get(
        f"{BASE_URL}/lists",
        headers=headers,
        params={"fields[list]": "name"},
    )
    if resp.status_code != 200:
        print(f"[klaviyo] lists error: {resp.text[:200]}", flush=True)
        return 0

    list_id = None
    for item in resp.json().get("data", []):
        name = item.get("attributes", {}).get("name", "")
        print(f"[klaviyo] found list: '{name}' id={item.get('id')}", flush=True)
        if name.lower() == list_name.lower():
            list_id = item["id"]
            break

    if not list_id:
        print(f"[klaviyo] list '{list_name}' not found", flush=True)
        return 0

    # Step 2: try additional-fields[list]=profile_count
    list_resp = await client.get(
        f"{BASE_URL}/lists/{list_id}",
        headers=headers,
        params={"additional-fields[list]": "profile_count"},
    )
    print(f"[klaviyo] list detail status: {list_resp.status_code}", flush=True)
    if list_resp.status_code == 200:
        attrs = list_resp.json().get("data", {}).get("attributes", {})
        print(f"[klaviyo] list '{list_name}' attrs: {attrs}", flush=True)
        count = attrs.get("profile_count")
        if count is not None:
            return int(count)

    # Step 3: fallback — paginate through profiles and count (capped to avoid hanging on large lists)
    print(f"[klaviyo] falling back to profile pagination for '{list_name}'", flush=True)
    total = 0
    next_url = f"{BASE_URL}/lists/{list_id}/profiles"
    params: dict = {"page[size]": 100, "fields[profile]": "id"}
    max_pages = 10  # cap at 1,000 profiles to avoid multi-minute hangs on large lists
    pages_fetched = 0
    while next_url and pages_fetched < max_pages:
        page_resp = await client.get(next_url, headers=headers, params=params)
        if page_resp.status_code != 200:
            break
        body = page_resp.json()
        total += len(body.get("data", []))
        next_url = body.get("links", {}).get("next")
        params = {}  # next URL already includes all params
        pages_fetched += 1
    if next_url:
        print(f"[klaviyo] '{list_name}' pagination capped at {max_pages} pages, count={total}+", flush=True)
    else:
        print(f"[klaviyo] '{list_name}' paginated count={total}", flush=True)
    return total




def _last_6_weeks() -> list[tuple]:
    """
    Return (start_dt, end_dt, label) for the last 6 complete Sun–Sat weeks, oldest first.
    Labels are like 'jan-e', 'feb-a', 'mar-a' — month abbreviation + letter counter.
    """
    from datetime import date, timedelta as td
    today = datetime.now(timezone.utc).date()
    # weekday(): Mon=0 … Sat=5, Sun=6  →  days back to most recent Saturday
    days_back_to_sat = (today.weekday() - 5) % 7
    last_sat = today - td(days=days_back_to_sat)

    raw_weeks = []
    for i in range(5, -1, -1):          # oldest first
        end_d = last_sat - td(weeks=i)
        start_d = end_d - td(days=6)
        start_dt = datetime(start_d.year, start_d.month, start_d.day, 0, 0, 0, tzinfo=timezone.utc)
        end_dt   = datetime(end_d.year,   end_d.month,   end_d.day,   23, 59, 59, tzinfo=timezone.utc)
        raw_weeks.append((start_dt, end_dt))

    month_counters: dict[str, int] = {}
    result = []
    for start_dt, end_dt in raw_weeks:
        end_date = end_dt.date()
        next_day = end_date + td(days=1)
        # Retail convention: the week ending on Jan 31 (when Feb 1 follows immediately)
        # is counted as the first week of February, not January.
        if end_date.month == 1 and next_day.month == 2:
            abbr = "feb"
        else:
            abbr = end_date.strftime("%b").lower()
        idx  = month_counters.get(abbr, 0)
        month_counters[abbr] = idx + 1
        label = f"{abbr}-{'abcdefghij'[idx]}"
        result.append((start_dt, end_dt, label))

    return result


async def get_weekly_email_revenue(client: httpx.AsyncClient) -> list[dict]:
    """
    Total email revenue (campaigns + flows) for the last 6 complete Sun–Sat weeks.
    Shape: [{label, start, end, campaign_revenue, flow_revenue, total}]
    """
    cached = _cache_get("weekly_revenue")
    if cached is not None:
        return cached

    headers = _headers()
    weeks = _last_6_weeks()

    conversion_metric_id = await _get_placed_order_metric_id(client, headers)

    full_start = weeks[0][0].isoformat()
    full_end   = weeks[-1][1].isoformat()

    # --- Campaigns: one report for the full 6-week window, bucket by send_date ---
    campaigns_resp = await client.get(
        f"{BASE_URL}/campaigns",
        headers=headers,
        params={
            "filter": (
                f"and(equals(messages.channel,'email'),"
                f"equals(status,'Sent'),"
                f"greater-or-equal(scheduled_at,{full_start}),"
                f"less-or-equal(scheduled_at,{full_end}))"
            ),
            "fields[campaign]": "name,scheduled_at,status",
        },
    )
    campaigns_resp.raise_for_status()
    campaign_list = campaigns_resp.json().get("data", [])

    revenue_by_campaign: dict[str, float] = {}
    if campaign_list:
        report_body: dict = {
            "data": {
                "type": "campaign-values-report",
                "attributes": {
                    "timeframe": {"start": full_start, "end": full_end},
                    "statistics": ["conversion_value"],
                },
            }
        }
        if conversion_metric_id:
            report_body["data"]["attributes"]["conversion_metric_id"] = conversion_metric_id

        report_resp = await _rate_limited_post(
            client, f"{BASE_URL}/campaign-values-reports", headers=headers, json=report_body
        )
        print(f"[klaviyo] weekly campaign-values-reports status: {report_resp.status_code}", flush=True)
        if report_resp.status_code == 200:
            for row in report_resp.json().get("data", {}).get("attributes", {}).get("results", []):
                cid = row.get("groupings", {}).get("campaign_id", "")
                revenue_by_campaign[cid] = (revenue_by_campaign.get(cid, 0.0)
                                            + float(row.get("statistics", {}).get("conversion_value") or 0))

    # Bucket campaign revenue into weeks by send_date
    campaign_rev_by_week: dict[str, float] = {lbl: 0.0 for _, _, lbl in weeks}
    for c in campaign_list:
        cid = c["id"]
        send_str = c.get("attributes", {}).get("scheduled_at", "")
        if not send_str:
            continue
        send_dt = datetime.fromisoformat(send_str.replace("Z", "+00:00"))
        for start_dt, end_dt, lbl in weeks:
            if start_dt <= send_dt <= end_dt:
                campaign_rev_by_week[lbl] += revenue_by_campaign.get(cid, 0.0)
                break

    # --- Flows: one report per week ---
    flows_resp = await client.get(
        f"{BASE_URL}/flows", headers=headers, params={"fields[flow]": "name,status"}
    )
    flows_resp.raise_for_status()
    all_flows = flows_resp.json().get("data", [])
    target_keywords = ["abandoned cart", "abandoned checkout", "back in stock"]
    flow_ids = [
        f["id"] for f in all_flows
        if any(kw in f.get("attributes", {}).get("name", "").lower() for kw in target_keywords)
    ]

    # One call for the full 6-week window instead of 6 separate calls.
    # Klaviyo flow reports don't support weekly date bucketing, so we distribute
    # the total flow revenue evenly across weeks (flows are continuous, not event-based).
    flow_rev_by_week: dict[str, float] = {lbl: 0.0 for _, _, lbl in weeks}
    if flow_ids:
        flow_body: dict = {
            "data": {
                "type": "flow-values-report",
                "attributes": {
                    "timeframe": {"start": full_start, "end": full_end},
                    "filter": f"contains-any(flow_id,[{','.join(repr(i) for i in flow_ids)}])",
                    "statistics": ["conversion_value"],
                    "group_by": ["flow_id", "flow_message_id"],
                },
            }
        }
        if conversion_metric_id:
            flow_body["data"]["attributes"]["conversion_metric_id"] = conversion_metric_id

        resp = await _rate_limited_post(
            client, f"{BASE_URL}/flow-values-reports", headers=headers, json=flow_body
        )
        print(f"[klaviyo] weekly flow-values-reports (full window) status: {resp.status_code}", flush=True)
        if resp.status_code == 200:
            total_flow_rev = sum(
                float(row.get("statistics", {}).get("conversion_value") or 0)
                for row in resp.json().get("data", {}).get("attributes", {}).get("results", [])
            )
            # Distribute evenly across the 6 weeks
            per_week = round(total_flow_rev / len(weeks), 2) if weeks else 0.0
            for _, _, lbl in weeks:
                flow_rev_by_week[lbl] = per_week

    result = []
    for start_dt, end_dt, lbl in weeks:
        c_rev = round(campaign_rev_by_week.get(lbl, 0.0), 2)
        f_rev = round(flow_rev_by_week.get(lbl, 0.0), 2)
        result.append({
            "label": lbl,
            "start": start_dt.date().isoformat(),
            "end":   end_dt.date().isoformat(),
            "campaign_revenue": c_rev,
            "flow_revenue":     f_rev,
            "total":            round(c_rev + f_rev, 2),
        })

    # Only cache if we got real data (same pattern as campaigns/flows)
    if any(r["total"] > 0 for r in result):
        _cache_set("weekly_revenue", result)
    return result


async def get_email_revenue(client: httpx.AsyncClient) -> float:
    """Total email revenue this month (campaigns + flows)."""
    payload = await get_campaign_performance(client)
    campaigns = payload.get("campaigns", [])
    flows = await get_flow_performance(client)
    campaign_rev = sum(c["revenue"] for c in campaigns)
    flow_rev = sum(f["revenue"] for f in flows)
    print(f"[klaviyo] email revenue breakdown: campaigns={campaign_rev} ({len(campaigns)} campaigns) flows={flow_rev} ({len(flows)} flows) total={campaign_rev + flow_rev}", flush=True)
    for f in flows:
        print(f"[klaviyo]   flow '{f['name']}' revenue={f['revenue']}", flush=True)
    return round(campaign_rev + flow_rev, 2)
