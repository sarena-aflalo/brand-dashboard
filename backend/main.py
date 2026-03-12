"""
AFLALO Brand Revenue Dashboard — FastAPI Backend

Run with:
  uvicorn main:app --reload --port 8000

Endpoints:
  GET /api/email/campaigns       → Campaign performance
  GET /api/email/flows           → Always-on flow performance
  GET /api/email/subscribers     → Subscriber growth + source breakdown
  GET /api/influencer/creators   → Creator performance (ShopMy stub)
  GET /api/paid/creatives        → Meta ad creative performance
  GET /api/kpi                   → Aggregated KPI strip data
"""

import os
import asyncio
import httpx
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import klaviyo
import shopmy
import meta

load_dotenv()

# Revenue goals (monthly) — adjust as needed
EMAIL_GOAL = 60_000.0
INFLUENCER_GOAL = 25_000.0
PAID_GOAL = 30_000.0


def _retail_month_paced_goal(goal: float) -> float:
    """
    Return the prorated email goal based on days elapsed in the current retail month.

    Retail month boundaries (retail calendar, Sun–Sat weeks):
      - Starts on the Sunday on or before the 1st of the calendar month
      - Ends on the last Saturday on or before the last day of the calendar month
    Example for March 2026: Mar 1 (Sun) → Mar 28 (Sat) = 28 days (mar-a through mar-d)
    """
    today = date.today()

    # Retail month start: Sunday on or before the 1st of the month
    first = date(today.year, today.month, 1)
    # weekday(): Mon=0 … Sun=6  →  days since last Sunday
    days_since_sunday = (first.weekday() + 1) % 7
    retail_start = first - timedelta(days=days_since_sunday)

    # Retail month end: last Saturday on or before the last day of the month
    if today.month == 12:
        last = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(today.year, today.month + 1, 1) - timedelta(days=1)
    days_since_saturday = (last.weekday() - 5) % 7
    retail_end = last - timedelta(days=days_since_saturday)

    total_days = (retail_end - retail_start).days + 1

    if today < retail_start:
        return 0.0
    if today >= retail_end:
        return goal

    days_elapsed = (today - retail_start).days + 1  # inclusive of today
    return goal * days_elapsed / total_days


async def _warmup():
    """Pre-fetch all data on startup so the first real request is fast."""
    try:
        async with _http_client() as client:
            await asyncio.gather(
                klaviyo.get_campaign_performance(client),
                klaviyo.get_flow_performance(client),
                klaviyo.get_subscriber_growth(client),
                klaviyo.get_weekly_email_revenue(client),
                shopmy.get_creator_performance(client),
                meta.get_creative_performance(client),
                return_exceptions=True,
            )
        print("[warmup] all data pre-fetched", flush=True)
    except Exception as e:
        print(f"[warmup] error (non-fatal): {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_warmup())
    yield


app = FastAPI(title="AFLALO Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://brand-dashboard-ux2x.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


def _status_badge(actual: float, goal: float) -> str:
    if goal == 0:
        return "on_track"
    pct = actual / goal
    if pct > 1.0:
        return "ahead"
    if pct >= 0.90:
        return "on_track"
    if pct >= 0.70:
        return "needs_attention"
    return "behind"


# ---------------------------------------------------------------------------
# Email endpoints
# ---------------------------------------------------------------------------




@app.get("/api/email/campaigns")
async def email_campaigns():
    try:
        async with _http_client() as client:
            data = await klaviyo.get_campaign_performance(client)
        return {"status": "ok", "campaigns": data.get("campaigns", []), "ytd": data.get("ytd", {})}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Klaviyo API error: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/email/flows")
async def email_flows():
    try:
        async with _http_client() as client:
            data = await klaviyo.get_flow_performance(client)
        return {"status": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Klaviyo API error: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/email/weekly-revenue")
async def email_weekly_revenue():
    try:
        async with _http_client() as client:
            data = await klaviyo.get_weekly_email_revenue(client)
        return {"status": "ok", "weeks": data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Klaviyo API error: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/email/subscribers")
async def email_subscribers():
    try:
        async with _http_client() as client:
            data = await klaviyo.get_subscriber_growth(client)
        return {"status": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Klaviyo API error: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Influencer endpoints
# ---------------------------------------------------------------------------


@app.get("/api/influencer/creators")
async def influencer_creators():
    try:
        async with _http_client() as client:
            data = await shopmy.get_creator_performance(client)
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Paid endpoints
# ---------------------------------------------------------------------------


@app.get("/api/paid/creatives")
async def paid_creatives():
    try:
        async with _http_client() as client:
            data = await meta.get_creative_performance(client)
        return {"status": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Meta API error: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Image proxy — streams Facebook CDN images to avoid hotlink 403s
# ---------------------------------------------------------------------------


@app.get("/api/proxy/image")
async def proxy_image(url: str = Query(...)):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        print(f"[proxy] {resp.status_code} {url[:80]}", flush=True)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Image fetch failed")
        content_type = resp.headers.get("content-type", "image/jpeg")
        return Response(content=resp.content, media_type=content_type)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------------------------------------------------------------------------
# KPI strip — fetches all three revenue numbers in parallel
# ---------------------------------------------------------------------------


@app.get("/api/kpi")
async def kpi():
    async with _http_client() as client:
        results = await asyncio.gather(
            klaviyo.get_email_revenue(client),
            shopmy.get_influencer_revenue(client),
            meta.get_paid_revenue(client),
            klaviyo.get_subscriber_growth(client),
            return_exceptions=True,
        )

    email_rev, influencer_rev, paid_rev, subscriber_data = results

    def _safe(val, goal: float, pace_goal: float = None) -> dict:
        if isinstance(val, Exception):
            return {
                "actual": None,
                "goal": goal,
                "pct": None,
                "status": "error",
                "error": str(val),
            }
        pct = round(val / goal * 100, 1) if goal else None
        return {
            "actual": val,
            "goal": goal,
            "pct": pct,
            "status": _status_badge(val, pace_goal if pace_goal is not None else goal),
            "error": None,
        }

    email_paced_goal = _retail_month_paced_goal(EMAIL_GOAL)

    # Subscriber KPI — extract net_new from the subscriber growth dict
    SUB_GOAL = 500
    if isinstance(subscriber_data, Exception):
        sub_kpi = {"actual": None, "goal": SUB_GOAL, "pct": None, "status": "error", "error": str(subscriber_data)}
    else:
        net_new = subscriber_data.get("net_new", 0)
        sub_kpi = _safe(float(net_new), float(SUB_GOAL))

    return {
        "subscribers": sub_kpi,
        "email": _safe(email_rev, EMAIL_GOAL, pace_goal=email_paced_goal),
        "influencer": _safe(influencer_rev, INFLUENCER_GOAL),
        "paid": _safe(paid_rev, PAID_GOAL),
    }


# ---------------------------------------------------------------------------
# Serve frontend — must be registered AFTER all /api routes
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
