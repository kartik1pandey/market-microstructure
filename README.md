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
| DS-analytics | Event study: does an outage/change shift spread or VPIN? Interrupted time-series + synthetic control | Data science roles |
| Alpha (quant researcher) | Avellaneda-Stoikov market-making + Almgren-Chriss execution, backtested against real data | Quant research roles |
| Risk (quant analyst) | Rolling VaR / expected shortfall, VPIN-based adverse-selection attribution | Quant risk roles |

## Status

Early build — in progress.

## Repo layout

- `ingestion/` — async WebSocket client, order-book reconstruction, Parquet writer
- `dbt/` — feature transforms (spread, depth, order-flow imbalance, VPIN, realized vol)
- `dags/` — Airflow orchestration
- `alpha/` — Avellaneda-Stoikov and Almgren-Chriss implementations + backtests
- `risk/` — VaR/ES engine, VPIN-based P&L attribution
- `dashboards/` — Looker Studio exports/links

## Grounding literature

- Avellaneda & Stoikov (2008), *High-frequency trading in a limit order book*
- Almgren & Chriss (2000), *Optimal execution of portfolio transactions*
- Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events*
- Easley, López de Prado & O'Hara (2012), *Flow Toxicity and Liquidity in a High-Frequency World*
