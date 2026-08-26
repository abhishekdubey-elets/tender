# GovIntel — Web (Next.js)

A modern SaaS frontend for the GovIntel sales-intelligence platform. Next.js 14
(App Router) + TypeScript + Framer Motion, dark-first with a light theme.

## What it does

Talks to the FastAPI backend through a **server-side proxy** (`app/api/[...path]/route.ts`)
so the API key stays server-side and there's no CORS. Features:

- Animated **leads board** — glass stat cards with count-up numbers, staggered
  card entrance, hover lift, animated score rings.
- **Filters** — min score, sector, product, event type, government org, status,
  and a debounced company search in the top bar.
- Spring-animated **detail drawer** — event, evidence (with source links + FACT/
  INFERENCE tags), company profile, opportunity reasoning, animated score-component
  bars, contact, AI sales brief + risk, source documents.
- **Feedback** controls that POST to the backend and update status live, with a
  toast.
- Theme toggle (dark / light), skeleton loaders, reduced-motion support.

## Run (dev)

The backend must be running first (Postgres + FastAPI on port 8000):

```bash
# 1) database + API (from repo root / backend)
docker compose up -d db
cd backend && ./.venv/Scripts/python -m alembic upgrade head
./.venv/Scripts/python -m scripts.seed_demo_leads          # a few demo leads
./.venv/Scripts/python -m uvicorn "app.api:create_app" --factory --env-file .env --port 8000

# 2) web (this folder)
cd web && npm install && npm run dev
```

Open http://localhost:3000. Configure `web/.env.local`:

```
BACKEND_URL=http://127.0.0.1:8000
GOVINTEL_API_KEY=dev-local-key      # matches backend API_KEYS (dev only)
```

## Structure

- `app/page.tsx` — dashboard orchestrator (state, stats, filters, grid)
- `app/api/[...path]/route.ts` — server-side proxy to the backend
- `components/` — app shell, lead card, detail drawer, animated UI primitives
- `lib/` — typed API client + types
- `app/globals.css`, `app/components.css` — design system + component styles
