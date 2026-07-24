# Project Context – IGDB Data Engineering Pipeline

## Overview

This project is an end-to-end data engineering pipeline built to demonstrate modern data stack skills for resume and interview purposes.

The pipeline ingests video game data from IGDB, stores raw data in PostgreSQL, transforms it using dbt, and exposes analytics through a Streamlit app with an optional AI summarization layer.

---

## Goals

* Build a resume-quality data engineering project
* Learn and demonstrate:

  * API ingestion with authentication
  * PostgreSQL data modeling
  * dbt transformations (staging → intermediate → marts)
  * Docker-based local development
  * Airflow orchestration
  * Optional AI integration

---

## Architecture

IGDB API → Python ingestion → Raw PostgreSQL → dbt → Analytics tables → Streamlit / AI

Key principles:

* Python handles ingestion and raw loading
* dbt handles transformations and modeling
* App/AI layer only reads from curated dbt models

---

## Current Progress

Completed:

* Project scaffolding
* dbt project initialization
* IGDB authentication (OAuth via Twitch)
* IGDB API client
* Initial ingestion for games endpoint
* Raw data loading into PostgreSQL

Next Steps:

* Expand ingestion to additional entities (genres, platforms, companies)
* Introduce dbt source + staging models
* Build analytics marts

---

## Data Source

API: IGDB

Auth:

* igdb_client_id (env)
* igdb_client_secret (env)
* OAuth token retrieved via Twitch

Important notes:

* IGDB uses POST-based query language
* Requires token + client ID in headers

---

## Key Tables (Planned)

Raw:

* raw_games
* raw_genres
* raw_platforms
* raw_companies
* raw_involved_companies

dbt:

* staging models (stg_*)
* intermediate models (relationships)
* mart models (analytics-ready)

---

## Tech Stack

* Python 3.11
* PostgreSQL
* dbt Core
* Docker / Docker Compose
* Apache Airflow
* Streamlit
* OpenAI API (optional)

---

## Workflow

* Codex is used to generate and modify code
* ChatGPT is used to:

  * explain code
  * debug issues
  * guide architecture decisions

---

## Current Focus

Understanding and reviewing:

* ingestion logic
* API client
* authentication flow
* dependencies and imports

---

## Notes

* .env is used for all secrets
* Environment variables are loaded via dotenv
* Project is intentionally iterative, not over-engineered
* Priority is building something explainable in interviews
