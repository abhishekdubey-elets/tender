# Deploy the GovIntel backend to Render (free, Docker)

Same container as the HF package, on Render's free web-service tier — no PRO needed.
Your repo already tracks `origin/main`, so Render can build straight from GitHub.

## Steps

1. **Push the latest code** (the render.yaml + port-flexible Dockerfile):
   ```
   git push
   ```
2. **Render → New → Blueprint**, pick this GitHub repo. Render reads
   `deploy/render/render.yaml` and creates the `govintel-backend` web service
   (Docker, free plan, health check `/health`).
   *(Or: New → Web Service → Docker → set Dockerfile path `deploy/huggingface/Dockerfile`,
   root/context `backend`.)*
3. In the service's **Environment**, add the two secrets (the render.yaml marks them
   `sync:false`, so they're not stored in the repo):
   - `API_KEYS` = `{"<YOUR-STRONG-RANDOM-KEY>":"11111111-1111-1111-1111-111111111111:analyst"}`
   - `MONGODB_URI` = your `mongodb+srv://…` from `backend/.env` (rotated password)
   (`USE_MONGO=true` and `MONGODB_DB=govintel` come from render.yaml.)
4. **Atlas → Network Access**: add `0.0.0.0/0` (Render egress IPs are dynamic on the
   free tier), with a strong DB password + least-privilege user.

## Verify

```
curl https://govintel-backend.onrender.com/health
curl -H "X-API-Key: <YOUR-STRONG-RANDOM-KEY>" https://govintel-backend.onrender.com/api/leads
```

## Notes

- Free web services **sleep after ~15 min idle** and cold-start on the next request
  (~30–60 s) — fine for a demo; the 24h crawl scheduler pauses while asleep.
- WebSocket push (`/ws`) works on Render.
- Point the Next dashboard here by setting its `BACKEND_URL` to the Render URL and
  `GOVINTEL_API_KEY` to the `API_KEYS` key above.
- Alternatives with the same Dockerfile: **Fly.io**, **Koyeb**, **Railway**.
