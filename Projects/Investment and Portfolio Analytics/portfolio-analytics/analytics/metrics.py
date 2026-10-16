"""Return, risk and portfolio metrics. All functions are pure pandas/numpy."""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def cumulative_growth(returns: pd.DataFrame | pd.Series, base: float = 100.0):
    """Growth of `base` invested at the start."""
    return base * (1 + returns).cumprod()


def annualised_return(returns: pd.Series) -> float:
    """Geometric (CAGR-style) annualised return."""
    growth = (1 + returns).prod()
    years = len(returns) / TRADING_DAYS
    return growth ** (1 / years) - 1


def annualised_volatility(returns: pd.Series) -> float:
    return returns.std() * np.sqrt(TRADING_DAYS)


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Percent decline from the running peak (0 at highs, negative below)."""
    wealth = (1 + returns).cumprod()
    return wealth / wealth.cummax() - 1


def max_drawdown(returns: pd.Series) -> float:
    return drawdown_series(returns).min()


def sharpe_ratio(returns: pd.Series, rf: float = 0.0) -> float:
    """rf is an annual risk-free rate (e.g. 0.12 for a Kenyan T-bill proxy)."""
    ann_ret = annualised_return(returns)
    vol = annualised_volatility(returns)
    return (ann_ret - rf) / vol if vol else np.nan


def sortino_ratio(returns: pd.Series, rf: float = 0.0) -> float:
    downside = returns[returns < 0].std() * np.sqrt(TRADING_DAYS)
    return (annualised_return(returns) - rf) / downside if downside else np.nan


def historical_var(returns: pd.Series, level: float = 0.95) -> float:
    """1-day historical Value-at-Risk (a positive loss number)."""
    return -returns.quantile(1 - level)


def summary_table(returns: pd.DataFrame, rf: float = 0.0) -> pd.DataFrame:
    rows = {}
    for col in returns.columns:
        r = returns[col]
        rows[col] = {
            "Ann. return": annualised_return(r),
            "Ann. volatility": annualised_volatility(r),
            "Sharpe": sharpe_ratio(r, rf),
            "Sortino": sortino_ratio(r, rf),
            "Max drawdown": max_drawdown(r),
            "VaR 95% (1d)": historical_var(r),
        }
    return pd.DataFrame(rows).T


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def portfolio_returns(returns: pd.DataFrame, weights: pd.Series,
                      rebalance: str | None = "ME") -> pd.Series:
    """Portfolio daily returns with periodic rebalancing back to target weights.

    rebalance: pandas offset alias ('ME' = month end) or None for buy-and-hold.
    """
    w = weights.reindex(returns.columns).fillna(0.0).values
    if rebalance is None:
        holdings = w.copy()
        out = []
        for _, row in returns.iterrows():
            r = (holdings * row.values).sum() / holdings.sum()
            out.append(r)
            holdings = holdings * (1 + row.values)
        return pd.Series(out, index=returns.index, name="portfolio")

    rebalance_days = set(returns.groupby(returns.index.to_period(rebalance[0])).tail(1).index)
    holdings = w.copy()
    out = []
    for date, row in returns.iterrows():
        total = holdings.sum()
        out.append((holdings * row.values).sum() / total)
        holdings = holdings * (1 + row.values)
        if date in rebalance_days:
            holdings = w * holdings.sum()
    return pd.Series(out, index=returns.index, name="portfolio")


def rolling_volatility(returns: pd.Series, window: int = 60) -> pd.Series:
    return returns.rolling(window).std() * np.sqrt(TRADING_DAYS)
