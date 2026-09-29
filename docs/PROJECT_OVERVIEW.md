# Project Overview

## Purpose

Build a production-style local data platform that ingests video-game metadata from IGDB, preserves raw source data in PostgreSQL, transforms it with dbt, orchestrates repeatable pipeline runs with Airflow, and exposes curated analytics through a lightweight Streamlit application.

The project is intentionally scoped as a data-engineering portfolio project. The goal is not to build the largest possible platform; it is to demonstrate a coherent, reliable, testable pipeline whose design decisions can be explained clearly.

## Core use cases

The curated data should support questions such as:

- How have game releases changed over time?
- Which genres and platforms have the most highly rated games?
- How does publisher/developer output vary over time?
- Which games, companies, genres, and platforms are related?

## Target stack

- Python 3.11+ — API ingestion and raw loading
- IGDB API / Twitch OAuth — source and authentication
- PostgreSQL — raw and analytics storage
- dbt Core — transformations, tests, and documentation
- Docker Compose — reproducible local services
- Apache Airflow — orchestration and scheduling
- Streamlit — thin analytics/consumption layer
- pytest — Python unit tests

## Scope decisions

### In scope

- Authenticated API ingestion with retry handling
- Multiple related IGDB entities
- Idempotent/upsert-based raw loading
- Incremental ingestion strategy based on source update timestamps
- Raw payload retention for traceability
- Layered dbt modeling: staging → intermediate → marts
- dbt schema/data tests
- Repeatable orchestration
- Containerized local development
- A small analytics UI that reads curated models
- Clear operational and architecture documentation

### Deferred / optional

An LLM-generated summary layer was part of the original idea. It is intentionally deferred until the core data platform is complete. It adds little value if ingestion, modeling, testing, orchestration, and reproducibility are unfinished.

## Success criteria

The project is complete when a new developer can clone the repository, configure credentials, start the required services, run the pipeline end-to-end, execute tests, and inspect analytics outputs using documented commands.

A successful end-to-end run should:

1. authenticate with Twitch/IGDB;
2. ingest configured IGDB entities;
3. upsert raw records into PostgreSQL;
4. run dbt models and tests;
5. complete through Airflow without manual pipeline steps; and
6. make curated analytics available to Streamlit.

## Design principles

- Python ingests; dbt transforms.
- Preserve source payloads at the raw boundary.
- Prefer idempotent operations so reruns are safe.
- Build incrementally and keep each change reviewable.
- Favor simple, explainable designs over unnecessary infrastructure.
- Treat tests, logging, documentation, and reproducibility as part of the pipeline rather than polish added at the end.
