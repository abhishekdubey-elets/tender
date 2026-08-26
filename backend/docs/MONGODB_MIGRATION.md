# MongoDB migration — Phase 1 (serving layer)

Phase 1 makes the **dashboard serve from MongoDB Atlas** while the Postgres path
stays intact behind a flag. Board, lead detail, feedback writes, and the live
WebSocket push all run on Mongo; the ingestion pipeline still writes Postgres
(that's Phase 2).

## What's included

- `app/api/mongo_repository.py` — `MongoLeadRepository` (board / detail / feedback)
  over a single denormalized `leads` collection, plus `ensure_indexes()` and a
  **change-stream** watcher that drives the WebSocket push (replaces LISTEN/NOTIFY).
- `scripts/export_to_mongo.py` — copies the current Postgres leads into Atlas.
- Config flags in `app/config.py`; repository + push wired in `app/api/main.py`.

## Run it (on your machine — never from this session)

1. **Rotate the Atlas password** (it was pasted in chat) and, in Atlas → Network
   Access, allow-list the IP you'll run from.
2. Put the secret in the **git-ignored** `backend/.env`:
   ```
   USE_MONGO=true
   MONGODB_URI=mongodb+srv://<user>:<pass>@cluster0.7zyshvk.mongodb.net/?appName=Cluster0
   MONGODB_DB=govintel
   ```
3. Install the driver: `pip install "pymongo[srv]>=4.6"` (already in pyproject).
4. Export existing leads (needs Postgres up):
   ```
   python -m scripts.export_to_mongo
   ```
5. Start the API — it now serves from Atlas:
   ```
   uvicorn app.api:create_app --factory --port 8000
   ```
   The board reads Mongo; feedback writes Mongo; edits stream back to the dashboard
   over the same WebSocket. `USE_MONGO` takes precedence over `USE_DB_REPOSITORY`.

## Notes / limits

- **Change streams need a replica set** — Atlas is one, so the push works there
  (it won't on a standalone local mongod).
- **Sorting**: `event_date` (a real date) descending → newest first; undated
  (news) leads sort last, matching the Postgres board.
- **Not yet migrated (Phase 2/3)**: the crawl/seed still write Postgres; Atlas
  Vector Search index for dedup/retrieval; retiring Alembic and porting the test
  suite (`mongomock` or a throwaway test DB).
