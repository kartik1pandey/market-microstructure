# Market Microstructure & Optimal Execution

[![tests](https://github.com/kartik1pandey/market-microstructure/actions/workflows/tests.yml/badge.svg)](https://github.com/kartik1pandey/market-microstructure/actions/workflows/tests.yml)

Live limit-order-book data captured from Binance, turned into genuine microstructure
signals, feeding two closed-form quant-finance models end to end — not a downloaded CSV,
not a toy simulation.

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Apache Airflow](https://img.shields.io/badge/Airflow-017CEE?style=for-the-badge&logo=apacheairflow&logoColor=white)
![dbt](https://img.shields.io/badge/dbt-FF694B?style=for-the-badge&logo=dbt&logoColor=white)
![Google BigQuery](https://img.shields.io/badge/BigQuery-4285F4?style=for-the-badge&logo=googlebigquery&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Looker Studio](https://img.shields.io/badge/Looker_Studio-4285F4?style=for-the-badge&logo=looker&logoColor=white)

## One pipeline, four lenses

Raw ticks (Binance WebSocket) → local Parquet lake → dbt (feature transforms) →
BigQuery (warehouse) → four lenses:

| Lens | What it does | Targets |
|---|---|---|
| BIE | Liquidity/health dashboard — spread, depth, VPIN over time | BI/analytics engineer roles |
| DS-analytics | Event study: did ending a fee promotion shift BTC/TUSD liquidity? Synthetic control + placebo test | Data science roles |
| Alpha (quant researcher) | Avellaneda-Stoikov market-making + Almgren-Chriss execution, calibrated and backtested against real captured data | Quant research roles |
| Risk (quant analyst) | Rolling VaR/ES + Kupiec backtest, VPIN-based P&L attribution, alerting wired into Airflow | Quant risk roles |

## Status

All 7 build phases complete, 63 passing tests, CI green on every push. Ingestion captured a
multi-hour BTC/USDT session (spanning real price movement, not just a quiet flat window),
loaded into BigQuery, and then **deliberately paused** — the dashboard below is a stable
snapshot of that captured session rather than a live feed, so it looks the same to anyone
opening it later rather than depending on an always-on cloud process (see "Why not
continuous cloud ingestion?" below).

**Dashboard:** [Market Microstructure — Liquidity & Health (Looker Studio)](https://datastudio.google.com/reporting/05ccadec-b4e3-44b4-ae57-c69aac22b663)

## Architecture

```mermaid
flowchart TB
    binance[["Binance WebSocket<br/>live L2 depth + trades"]]
    ingest["ingestion/binance/main.py<br/>order-book reconstruction"]
    parquet[("Local Parquet lake")]
    ge{{"Great Expectations<br/>checkpoint"}}
    loader["warehouse/load_raw.py"]
    duckdb[("DuckDB (dev)")]
    bigquery[("BigQuery (prod)")]
    dbt_models["dbt models<br/>spread · order-flow imbalance · VPIN"]
    airflow["Airflow (Docker)<br/>orchestrates the above on a schedule"]

    dashboard["Looker Studio dashboard"]
    dsanalytics["Causal case study<br/>(synthetic control)"]
    alpha["Alpha backtest<br/>Avellaneda-Stoikov · Almgren-Chriss"]
    risk["Risk checks<br/>VaR/ES · Kupiec · alerts"]

    binance -->|"depth diffs + trades"| ingest
    ingest -->|"flush every 500 rows"| parquet
    parquet -->|"validates raw ticks"| ge
    ge -->|"pass"| loader
    loader -->|"CREATE OR REPLACE"| duckdb
    loader -->|"CREATE OR REPLACE"| bigquery
    airflow -.->|"schedules load -> GE -> dbt -> test -> risk check"| loader

    duckdb --> dbt_models
    bigquery --> dbt_models

    dbt_models --> dashboard
    dbt_models --> dsanalytics
    dbt_models --> alpha
    dbt_models --> risk

    risk -->|"VaR breach or<br/>toxic VPIN regime"| alertfire(["Alert fires"])
```

### Why not continuous cloud ingestion?

A cloud deployment (Render) was built and tested: a worker streaming ticks straight into
BigQuery, and a cron job running the transform/risk pipeline every 15 minutes. It worked —
until checking actual Render pricing showed Background Workers and Cron Jobs aren't part of
the free tier, only web services with spin-down are. Running a 24/7 worker plus a scheduled
job indefinitely isn't worth the ongoing cost for a portfolio project, so the cloud path was
dropped in favor of a **captured-and-paused** snapshot: ingest a real, multi-hour session
once, load it into BigQuery, and stop. The dashboard reads a stable dataset either way — it
doesn't know or care whether the underlying pipeline is still running. The code for the
cloud path (`ingestion/binance/bigquery_writer.py`) is still in the repo and still tested,
since it's genuine, working infrastructure - just not deployed, for a cost reason stated
honestly rather than silently abandoned.

## What's actually in here

- **Ingestion** (`ingestion/binance/`): async WebSocket client reconstructing the live order
  book from Binance's diff-depth stream, with sequence-gap detection and reconnect-with-backoff.
- **Lake → warehouse** (`warehouse/`): local Parquet lake, loaded into DuckDB (dev) or
  BigQuery (prod) — same dbt models run against either target unchanged.
- **Transform** (`dbt/`): spread, depth, order-flow imbalance, and VPIN (real Bulk Volume
  Classification via a hand-implemented normal-CDF SQL macro — not a shortcut using the
  exchange's trade-side flag).
- **Data quality** (`data_quality/`): Great Expectations checkpoint, verified to actually
  catch injected bad data, not just pass on good data.
- **Orchestration** (`dags/`): Airflow (Docker), two lanes (dev/DuckDB, prod/BigQuery) off a
  shared data-quality gate, plus a risk-check task.
- **Causal case study** (`ds_analytics/`): pre-registered synthetic-control event study on a
  real, dated Binance fee-policy change — reports both the pre-registered (null) result and
  a clearly-labeled exploratory follow-up, not just whichever looked better.
- **Alpha** (`alpha/`): Avellaneda-Stoikov and Almgren-Chriss, calibrated from captured tick
  data (not textbook constants), backtested walk-forward against a naive baseline.
- **Risk** (`risk/`): rolling VaR/ES, Kupiec proportion-of-failures test, VPIN-based P&L
  attribution, and alerting rules wired into the live Airflow DAG.

## Screenshots

<!-- Screenshots added below - see screenshots/ -->

## Running it

```
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Ingest live ticks (Ctrl+C to stop, flushes cleanly)
python -m ingestion.binance.main BTCUSDT

# Load the lake into a warehouse and run the transforms
python -m warehouse.load_raw --target dev        # dev only - prod needs --confirm-prod-overwrite
cd dbt && dbt run --profiles-dir . --target dev

# Reproduce the causal case study / backtest / risk check
python -m ds_analytics.run_analysis --interval 1h
python -m alpha.run_backtest
python -m risk.run_risk_checks

# Tests
python -m pytest tests/ -v

# Full local orchestration (Airflow, Docker Desktop required)
docker compose up -d   # then open http://localhost:8080
```

## Grounding literature

- Avellaneda & Stoikov (2008), *High-frequency trading in a limit order book*
- Almgren & Chriss (2000), *Optimal execution of portfolio transactions*
- Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events*
- Easley, López de Prado & O'Hara (2012), *Flow Toxicity and Liquidity in a High-Frequency World*

## License

MIT — see [LICENSE](LICENSE).
