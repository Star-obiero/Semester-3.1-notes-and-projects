# Investment and Portfolio Analytics Platform

Python analytics for historical returns, volatility, drawdowns, correlations and
portfolio allocation across NSE stocks and selected international assets.

> **Disclaimer:** All results are historical and describe the past only. They are not
> a guarantee or forecast of future performance and are not investment advice.

## What it does

| Module | Purpose |
|---|---|
| `analytics/data.py` | Load prices from CSV, align NSE / US / crypto calendars, simulated sample data |
| `analytics/metrics.py` | Returns, annualised volatility, drawdown, Sharpe, Sortino, historical VaR, correlations, rebalanced portfolio returns |
| `analytics/optimize.py` | Equal weight, minimum variance, maximum Sharpe, efficient frontier (long-only, 40% cap per asset) |
| `analytics/plots.py` | Growth, drawdown, correlation heatmap, frontier and allocation charts |
| `run_analysis.py` | Runs everything and writes CSVs and PNGs to `output/` |

## Quick start

```bash
pip install -r requirements.txt
python run_analysis.py                      # runs on SIMULATED sample data
python run_analysis.py --prices data/prices.csv --rf 0.10 --benchmark SPY
```

`data/prices.csv` format: a `date` column plus one adjusted-close column per ticker.
Keep tickers in `ASSETS` (in `analytics/data.py`) so each is labelled NSE or INTL.
Without a prices file the sample data is simulated and every chart says so.

## Method notes

- **Returns:** simple daily returns; annualised return is geometric, volatility is daily std x sqrt(252).
- **Frontier and optimiser** use arithmetic mean returns, so their return figures differ slightly from the geometric returns in the summary tables.
- **Rebalancing:** portfolios rebalance to target weights at each month end.
- **Calendars:** gaps of up to 5 days are forward-filled; remaining missing dates are dropped.
- **Currency:** prices are used in their own currency. For a KES-based view, convert international assets with a KES/USD series before analysis.
- **Optimiser caveat:** mean-variance weights are sensitive to noisy historical estimates; treat them as an illustration of the method, not a recommendation.

## Real data and the SQLite store

```bash
pip install -r requirements.txt
# 1. International assets from Yahoo Finance (SPY, GLD, BTC-USD)
python -m analytics.ingest --db data/portfolio.db --yahoo --start 2020-01-01
# 2. NSE stocks from CSV files, one per ticker (data/nse/SCOM.csv, EQTY.csv, ...)
python -m analytics.ingest --db data/portfolio.db --nse-dir data/nse
# 3. Analyse straight from the database
python run_analysis.py --db data/portfolio.db --start 2021-01-01 --rf 0.10
```

- **NSE CSV format:** a date column (`Date`/`date`) and a price column (`Adj Close`, `Close` or `Price`).
  Thousands separators are handled. Use adjusted prices where available, and check for splits and
  dividend gaps, as free NSE data is often unadjusted.
- **Re-running is safe:** rows are upserted by (date, ticker), so you can ingest daily without duplicates.
- **Freshness check:** `SELECT * FROM latest_prices;` shows the last date and row count per ticker.
- **Currencies:** NSE prices are in KES; SPY and GLD in USD; BTC-USD in USD. Returns are computed in each
  asset's own currency. A combined KES-based portfolio would need a KES/USD series.
- When a database is used, charts no longer carry the "SIMULATED" label, so make sure the database
  holds real data.

## Next steps

1. n8n workflow: scheduled ingestion, triggers `run_analysis.py`, sends a weekly summary.
2. Optional: KES/USD conversion for a single-currency view.
