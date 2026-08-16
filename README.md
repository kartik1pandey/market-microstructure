# Market Microstructure & Optimal Execution

Live limit-order-book data captured from Binance, turned into genuine microstructure
signals, feeding two closed-form quant-finance models end to end — not a downloaded CSV,
not a toy simulation.

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

All 7 build phases complete. 58 passing tests. Live dashboard, live Airflow orchestration,
live BigQuery warehouse.

**Dashboard:** [Market Microstructure — Liquidity & Health (Looker Studio)](https://datastudio.google.com/reporting/05ccadec-b4e3-44b4-ae57-c69aac22b663)

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

## Running it

```
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Ingest live ticks (Ctrl+C to stop, flushes cleanly)
python -m ingestion.binance.main BTCUSDT

# Load the lake into a warehouse and run the transforms
python -m warehouse.load_raw --target dev        # or --target prod (needs BigQuery creds)
cd dbt && dbt run --profiles-dir . --target dev

# Reproduce the causal case study / backtest / risk check
python -m ds_analytics.run_analysis --interval 1h
python -m alpha.run_backtest
python -m risk.run_risk_checks

# Tests
pytest tests/ -v

# Full orchestration (Airflow, Docker Desktop required)
docker compose up -d
```

## Grounding literature

- Avellaneda & Stoikov (2008), *High-frequency trading in a limit order book*
- Almgren & Chriss (2000), *Optimal execution of portfolio transactions*
- Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events*
- Easley, López de Prado & O'Hara (2012), *Flow Toxicity and Liquidity in a High-Frequency World*

## License

MIT — see [LICENSE](LICENSE).
