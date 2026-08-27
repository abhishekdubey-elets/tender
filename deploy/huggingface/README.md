---
title: GovIntel Backend
emoji: 🏛️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# GovIntel Backend

FastAPI lead-intelligence API served from **MongoDB Atlas**. This is the backend
only (no dashboard UI). It will not start serving data until the Space **secrets**
are set:

| Secret | Value |
|---|---|
| `USE_MONGO` | `true` |
| `MONGODB_URI` | `mongodb+srv://<user>:<pass>@cluster0.7zyshvk.mongodb.net/?appName=Cluster0` |
| `MONGODB_DB` | `govintel` |
| `API_KEYS` | `{"<your-strong-key>":"11111111-1111-1111-1111-111111111111:analyst"}` |

Health check: `GET /health`. All data endpoints require the `X-API-Key` header
(fail-closed — no valid key, no access). See `DEPLOY.md`.
