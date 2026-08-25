-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Ensures required extensions exist in the primary DB, then creates a
-- dedicated test database with the same extensions installed.

-- Primary database (connected as POSTGRES_DB=govintel).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- Create the test database if it does not already exist.
SELECT 'CREATE DATABASE govintel_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'govintel_test')\gexec

-- Install the extensions inside the test database too.
\connect govintel_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
