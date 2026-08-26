-- Instant-push triggers: emit a pg_notify('govintel_changed', <table>) whenever a
-- lead-relevant row changes. The API's WebSocket listener (app/api/ws.py) LISTENs
-- on this channel and fans a content-free "leads_changed" signal out to connected
-- dashboards, which then re-fetch through the authenticated HTTP API.
--
-- Idempotent: safe to re-run. Apply with:
--   docker exec -i anurag-sir-db-1 psql -U govintel -d govintel < scripts/notify_triggers.sql

CREATE OR REPLACE FUNCTION govintel_notify_change() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('govintel_changed', TG_TABLE_NAME);
  RETURN NULL;  -- AFTER trigger; return value ignored
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_opportunities_notify ON opportunities;
CREATE TRIGGER trg_opportunities_notify
  AFTER INSERT OR UPDATE OR DELETE ON opportunities
  FOR EACH ROW EXECUTE FUNCTION govintel_notify_change();

DROP TRIGGER IF EXISTS trg_lead_scores_notify ON lead_scores;
CREATE TRIGGER trg_lead_scores_notify
  AFTER INSERT OR UPDATE OR DELETE ON lead_scores
  FOR EACH ROW EXECUTE FUNCTION govintel_notify_change();
