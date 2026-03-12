# AFLALO Brand Dashboard

## Project structure
- `backend/` — FastAPI + Python (port 8000)
- `frontend/` — React + Vite + Tailwind (port 5173)

## Starting the backend
The backend uses a `.venv` virtual environment — must activate it first.
```
cd "C:\Users\saren\Documents\Brand Dashboard\aflalo-dashboard\backend"
.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

## Starting the frontend
```
cd "C:\Users\saren\Documents\Brand Dashboard\aflalo-dashboard\frontend"
npm run dev
```

## Restarting the backend (Windows)
```
taskkill /F /IM python.exe
cd "C:\Users\saren\Documents\Brand Dashboard\aflalo-dashboard\backend"
.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```
