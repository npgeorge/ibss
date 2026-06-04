-- Migration 001: Add unique constraint for idempotent insider upserts
--
-- insider_transactions was the only data table without a unique key, so
-- ON CONFLICT upserts had no index to target. This adds one matching the
-- ORM model (uq_insider_stock_date_name). Safe to run once on existing DBs.
--
-- De-duplicate any existing rows first (keep the lowest id per key),
-- then add the constraint.

DELETE FROM insider_transactions a
USING insider_transactions b
WHERE a.id > b.id
  AND a.stock_id = b.stock_id
  AND a.transaction_date = b.transaction_date
  AND a.insider_name = b.insider_name;

ALTER TABLE insider_transactions
    ADD CONSTRAINT uq_insider_stock_date_name
    UNIQUE (stock_id, transaction_date, insider_name);
