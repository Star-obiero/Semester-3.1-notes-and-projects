"""Data loading and a synthetic sample generator.

Real use: put a CSV in data/prices.csv with a `date` column and one adjusted-close
column per ticker. The sample generator exists only so the pipeline runs offline.
Sample prices are SIMULATED - they are not real market data.
"""
from pathlib import Path

import numpy as np
import pandas as pd

# Label each asset by market so the report can separate NSE from international.
ASSETS = {
    "SCOM": "NSE",   # Safaricom
    "EQTY": "NSE",   # Equity Group
    "KCB": "NSE",    # KCB Group
    "EABL": "NSE",   # East African Breweries
    "BAT": "NSE",    # BAT Kenya
    "SPY": "INTL",   # S&P 500 ETF
    "GLD": "INTL",   # Gold ETF
    "BTC": "INTL",   # Bitcoin
}

# Annual drift / volatility used ONLY for the simulation.
_SIM_PARAMS = {
    "SCOM": (0.10, 0.28), "EQTY": (0.12, 0.30), "KCB": (0.08, 0.32),
    "EABL": (0.06, 0.24), "BAT": (0.05, 0.22),
    "SPY": (0.10, 0.17), "GLD": (0.07, 0.15), "BTC": (0.35, 0.70),
}


def make_sample_prices(years: int = 5, seed: int = 42) -> pd.DataFrame:
    """Correlated geometric Brownian motion on business days."""
    rng = np.random.default_rng(seed)
    tickers = list(_SIM_PARAMS)
    n = len(tickers)
    days = years * 252
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)

    # Build a plausible correlation matrix: NSE names move together, SPY mildly,
    # gold and BTC mostly independent.
    corr = np.full((n, n), 0.10)
    nse = [i for i, t in enumerate(tickers) if ASSETS[t] == "NSE"]
    for i in nse:
        for j in nse:
            corr[i, j] = 0.45
    corr[tickers.index("SPY"), nse] = 0.20
    corr[nse, tickers.index("SPY")] = 0.20
    corr[tickers.index("BTC"), tickers.index("SPY")] = 0.30
    corr[tickers.index("SPY"), tickers.index("BTC")] = 0.30
    np.fill_diagonal(corr, 1.0)
    chol = np.linalg.cholesky(corr)

    mu = np.array([_SIM_PARAMS[t][0] for t in tickers])
    sigma = np.array([_SIM_PARAMS[t][1] for t in tickers])
    dt = 1 / 252
    shocks = rng.standard_normal((days, n)) @ chol.T
    log_ret = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
    start = np.array([30, 45, 40, 150, 400, 400, 170, 30000], dtype=float)
    prices = start * np.exp(np.cumsum(log_ret, axis=0))
    return pd.DataFrame(prices, index=dates, columns=tickers).rename_axis("date")


def load_prices(path: str | Path | None = None) -> pd.DataFrame:
    """Load prices from CSV, or fall back to simulated data if no file exists."""
    if path and Path(path).exists():
        df = pd.read_csv(path, parse_dates=["date"], index_col="date").sort_index()
        return clean_prices(df)
    return make_sample_prices()


def clean_prices(df: pd.DataFrame, max_gap: int = 5) -> pd.DataFrame:
    """Align calendars across markets.

    NSE and US markets have different holidays and BTC trades daily, so forward-fill
    short gaps (<= max_gap days) and drop dates where anything is still missing.
    """
    df = df[~df.index.duplicated(keep="last")]
    df = df.ffill(limit=max_gap)
    return df.dropna(how="any")
