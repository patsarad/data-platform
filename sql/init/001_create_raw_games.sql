CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.raw_games (
    igdb_id BIGINT PRIMARY KEY,
    name TEXT,
    slug TEXT,
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);
