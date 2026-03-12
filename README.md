# AFLALO Brand Revenue Dashboard

React + Vite frontend with a FastAPI Python backend.

## Quick start

### 1. Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

# Copy the env template and fill in your keys
cp .env.example .env

# Start the API server
uvicorn main:app --reload --port 8000
```

### 2. Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Environment variables (`backend/.env`)

| Variable | Description |
|---|---|
| `KLAVIYO_API_KEY` | Private API key from Klaviyo account settings |
| `SHOPMY_API_KEY` | ShopMy partnership API key (**stub until API access confirmed**) |
| `META_ACCESS_TOKEN` | Long-lived Meta Graph API user access token |
| `META_AD_ACCOUNT_ID` | Meta ad account ID (digits only, without `act_` prefix) |

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/kpi` | KPI strip — email / influencer / paid revenue vs goal |
| GET | `/api/email/campaigns` | Campaign performance table |
| GET | `/api/email/flows` | Abandoned Cart, Back in Stock, Welcome Series |
| GET | `/api/email/subscribers` | Subscriber growth + source breakdown |
| GET | `/api/influencer/creators` | Creator performance (ShopMy — stub) |
| GET | `/api/paid/creatives` | Meta ad creative performance |

---

## ShopMy status

ShopMy does not publish a public API. The `backend/shopmy.py` module returns
**mock data** so the Influencer tab renders correctly. When ShopMy provides API
credentials, replace the stub in `get_creator_performance()` with the real HTTP
call — the shape of the returned data matches exactly.

---

## Revenue goals (monthly)

Goals are set in `backend/main.py` as constants:

```python
EMAIL_GOAL       = 50_000.0
INFLUENCER_GOAL  = 25_000.0
PAID_GOAL        = 30_000.0
```

Adjust these to match your targets.
