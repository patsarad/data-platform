# Data Engineering Project – AI-Enhanced Gaming Analytics Pipeline

## 1. Objective

Build a production-style data engineering pipeline that ingests video game metadata from IGDB, stores raw data in PostgreSQL, transforms it using dbt, and exposes insights through a Streamlit app with an optional AI layer.

---

## 2. Use Case

Analyze video game trends such as:

* Top-rated games by platform or genre
* Release trends over time
* Publisher/developer output
* Franchise relationships

---

## 3. Tech Stack

* Python 3.11+
* PostgreSQL
* dbt Core
* Docker + Docker Compose
* Apache Airflow
* Streamlit
* OpenAI API (optional)
* IGDB API (via Twitch OAuth)

---

## 4. Architecture

IGDB API → Python Ingestion → Raw Postgres → dbt → Analytics Tables → App/AI

Key principle:

* Python = ingestion
* dbt = transformation

---

## 5. Data Source (IGDB)

Environment variables already set:

* igdb_client_id
* igdb_client_secret

Ingestion must:

1. Request OAuth token from Twitch
2. Use token for IGDB requests
3. Handle retries/errors

---

## 6. Project Structure

project-root/

* dags/
* src/

  * ingestion/
  * storage/
  * utils/
  * ai/
* dbt/

  * models/

    * staging/
    * intermediate/
    * marts/
* app/
* tests/
* data/
* docker/
* README.md
* PROJECT_PLAN.md
* AGENTS.md

---

## 7. Core Components

### Ingestion

* IGDB client
* OAuth token handling
* Raw data extraction
* Save to Postgres

### Raw Tables

* raw_games
* raw_genres
* raw_platforms
* raw_companies
* raw_involved_companies

### dbt Layers

* staging (cleaned tables)
* intermediate (joins)
* marts (analytics)

### App

* Streamlit UI
* Query dbt models

### AI Layer

* Summarize query results

---

## 8. Milestones

1. Repo + dbt setup
2. IGDB auth + client
3. Ingestion → Postgres
4. Raw schema design
5. dbt staging models
6. dbt marts
7. Docker
8. Airflow
9. Streamlit
10. AI layer
11. Testing + polish

---

## 9. dbt Strategy

* sources → raw tables
* staging → cleaned tables
* intermediate → relationships
* marts → analytics

Add:

* tests (not null, unique)
* documentation

---

## 10. Success Criteria

* Data ingested from IGDB
* Stored in Postgres
* dbt models run successfully
* Docker works
* Airflow orchestrates pipeline
* Streamlit app works
* Project is explainable in interviews

---

## 11. Resume Framing

Built an end-to-end gaming analytics pipeline using Python, PostgreSQL, dbt, Docker, and Airflow. Ingested authenticated IGDB API data, transformed it into analytics-ready models, and exposed insights through an app with optional AI summaries.
