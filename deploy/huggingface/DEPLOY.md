# Deploy the GovIntel backend to a Hugging Face Docker Space

The backend serves from MongoDB Atlas (Phase 1/2). This stands it up as a public
(or private) HTTPS API on Hugging Face.

## Read this first (security)

1. **Rotate the HF token** you pasted in chat — it's compromised. Use a fresh token.
2. **Atlas Network Access**: HF Spaces have **no static egress IP**, so the backend
   can only reach Atlas if you allow `0.0.0.0/0`. That opens your cluster to the
   internet — only acceptable with a **strong DB password** and a **least-privilege
   DB user** (read/write to `govintel` only). Rotate the Mongo password too.
3. **Space visibility**: a public Space exposes the API URL. The API is fail-closed
   (every data route needs a valid `X-API-Key`), but set the Space **Private** if you
   don't want it reachable at all. Use a strong `API_KEYS` value, not `dev-local-key`.
4. Secrets go in **Space → Settings → Variables and secrets**, never in the repo.

## Steps

```bash
# 1. Install the CLI and log in with your ROTATED token
pip install -U "huggingface_hub[cli]"
hf auth login                      # paste the new token

# 2. Create the Space (Docker SDK)
hf repo create govintel-backend --repo-type space --space_sdk docker
git clone https://huggingface.co/spaces/<your-username>/govintel-backend
cd govintel-backend

# 3. Assemble the Space repo: the Dockerfile + README + backend code
cp ../anurag-sir/deploy/huggingface/Dockerfile .
cp ../anurag-sir/deploy/huggingface/README.md .
cp ../anurag-sir/deploy/huggingface/.dockerignore .
cp -r ../anurag-sir/backend/app .
cp -r ../anurag-sir/backend/alembic .
cp    ../anurag-sir/backend/alembic.ini .

# 4. Push — the build starts automatically
git add -A && git commit -m "GovIntel backend" && git push
```

Then in **Space → Settings → Variables and secrets**, add the secrets from the table
in `README.md` (`USE_MONGO`, `MONGODB_URI`, `MONGODB_DB`, `API_KEYS`). The Space
rebuilds and starts serving.

## Verify

```bash
curl https://<your-username>-govintel-backend.hf.space/health
curl -H "X-API-Key: <your-key>" https://<your-username>-govintel-backend.hf.space/api/leads
```

`/health` → `{"status":"ok"}`; `/api/leads` → your leads from Atlas.

## Notes / limits

- WebSocket push (`/ws`) works on HF (Spaces support WebSockets); the dashboard
  would point `NEXT_PUBLIC_WS_URL` at `wss://<space>.hf.space/ws`.
- The 24h crawl scheduler runs inside the Space (it writes to Atlas). HF Spaces
  **sleep when idle** on the free tier, which pauses the scheduler — fine for a demo;
  use a paid tier or an external cron ping to keep it awake.
- To point the Next dashboard at this backend, set its `BACKEND_URL` to the Space URL
  and `GOVINTEL_API_KEY` to your `API_KEYS` key.
