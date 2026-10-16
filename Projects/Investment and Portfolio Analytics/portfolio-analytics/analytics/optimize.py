"""Portfolio allocation: equal weight, minimum variance, max Sharpe, efficient frontier.

All optimisation is long-only and fully invested. Inputs are HISTORICAL estimates,
so the output describes what would have been optimal in the past, not a forecast.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252


def _stats(weights, mu, cov):
    ret = float(weights @ mu)
    vol = float(np.sqrt(weights @ cov @ weights))
    return ret, vol


def _inputs(returns: pd.DataFrame):
    mu = returns.mean().values * TRADING_DAYS          # arithmetic annual mean
    cov = returns.cov().values * TRADING_DAYS
    return mu, cov


def equal_weight(returns: pd.DataFrame) -> pd.Series:
    n = returns.shape[1]
    return pd.Series(np.full(n, 1 / n), index=returns.columns)


def _optimise(objective, n, max_weight, extra_constraints=()):
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}, *extra_constraints]
    bounds = [(0.0, max_weight)] * n
    x0 = np.full(n, 1 / n)
    res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=cons)
    if not res.success:
        raise RuntimeError(f"Optimiser failed: {res.message}")
    return res.x


def min_variance(returns: pd.DataFrame, max_weight: float = 0.4) -> pd.Series:
    mu, cov = _inputs(returns)
    w = _optimise(lambda w: w @ cov @ w, len(mu), max_weight)
    return pd.Series(w, index=returns.columns)


def max_sharpe(returns: pd.DataFrame, rf: float = 0.0, max_weight: float = 0.4) -> pd.Series:
    mu, cov = _inputs(returns)

    def neg_sharpe(w):
        r, v = _stats(w, mu, cov)
        return -(r - rf) / v

    w = _optimise(neg_sharpe, len(mu), max_weight)
    return pd.Series(w, index=returns.columns)


def efficient_frontier(returns: pd.DataFrame, points: int = 25, max_weight: float = 0.4):
    """Min-variance portfolio for each target return. Returns a DataFrame."""
    mu, cov = _inputs(returns)
    n = len(mu)
    lo = _stats(min_variance(returns, max_weight).values, mu, cov)[0]
    hi = mu.max() * max_weight + np.sort(mu)[-2] * (1 - max_weight)  # reachable upper bound
    rows = []
    for target in np.linspace(lo, hi, points):
        cons = [{"type": "eq", "fun": lambda w, t=target: w @ mu - t}]
        try:
            w = _optimise(lambda w: w @ cov @ w, n, max_weight, cons)
        except RuntimeError:
            continue
        r, v = _stats(w, mu, cov)
        rows.append({"return": r, "volatility": v, **dict(zip(returns.columns, w))})
    return pd.DataFrame(rows)


def random_portfolios(returns: pd.DataFrame, n: int = 3000, seed: int = 1) -> pd.DataFrame:
    """Random long-only portfolios, used as a cloud behind the frontier."""
    rng = np.random.default_rng(seed)
    mu, cov = _inputs(returns)
    w = rng.dirichlet(np.ones(len(mu)), size=n)
    rets = w @ mu
    vols = np.sqrt(np.einsum("ij,jk,ik->i", w, cov, w))
    return pd.DataFrame({"return": rets, "volatility": vols})
