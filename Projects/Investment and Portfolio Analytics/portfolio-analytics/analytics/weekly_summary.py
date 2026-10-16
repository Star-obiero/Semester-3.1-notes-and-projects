
"""Generate a weekly portfolio summary for the n8n WhatsApp workflow."""
import argparse
import json
from pathlib import Path

import pandas as pd

from analytics import metrics
from analytics.ingest import read_prices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/portfolio.db")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--rf", type=float, default=0.10)
    parser.add_argument("--start", default="2021-01-01")
    args = parser.parse_args()

    prices = read_prices(args.db, start=args.start)

    if args.benchmark not in prices.columns:
        raise ValueError(
            f"Benchmark {args.benchmark} is missing from the database. "
            f"Available tickers: {list(prices.columns)}"
        )

    # Use the available history to calculate portfolio metrics.
    returns = metrics.daily_returns(prices)
    if returns.empty:
        raise ValueError("Not enough price history to calculate returns.")

    # Equal-weight portfolio across available non-benchmark assets.
    assets = [c for c in returns.columns if c != args.benchmark]
    if not assets:
        raise ValueError("No portfolio assets found.")

    portfolio_returns = returns[assets].mean(axis=1)
    benchmark_returns = returns[args.benchmark]

    # Compare the latest five trading sessions with the previous five.
    recent = portfolio_returns.tail(5)
    previous = portfolio_returns.iloc[-10:-5]

    if len(recent) < 5 or len(previous) < 5:
        raise ValueError("At least 10 trading sessions are needed.")

    recent_change = (1 + recent).prod() - 1
    previous_change = (1 + previous).prod() - 1
    change_pp = (recent_change - previous_change) * 100

    ann_return = metrics.annualised_return(portfolio_returns)
    ann_volatility = metrics.annualised_volatility(portfolio_returns)
    sharpe = metrics.sharpe_ratio(portfolio_returns, args.rf)
    max_dd = metrics.max_drawdown(portfolio_returns)
    benchmark_return = metrics.annualised_return(benchmark_returns)

    latest_date = prices.index[-1].strftime("%Y-%m-%d")
    latest_prices = prices.iloc[-1]
    top_ticker = max(assets, key=lambda t: returns[t].tail(5).add(1).prod())
    top_return = (returns[top_ticker].tail(5).add(1).prod() - 1) * 100

    # Exactly seven plain-text parameters for the approved WhatsApp template.
    params = [
        latest_date,
        f"{recent_change * 100:.2f}%",
        f"{change_pp:+.2f} percentage points",
        f"{ann_return * 100:.2f}%",
        f"{ann_volatility * 100:.2f}%",
        f"{sharpe:.2f}",
        f"{top_ticker} ({top_return:+.2f}%)",
    ]

    text = (
        f"Portfolio update as of {latest_date}. "
        f"Recent five-session return: {params[1]}. "
        f"Change versus the preceding five sessions: {params[2]}. "
        f"Annualised return: {params[3]}; volatility: {params[4]}; "
        f"Sharpe ratio: {params[5]}. "
        f"Top recent asset: {params[6]}. "
        f"Benchmark {args.benchmark} annualised return: "
        f"{benchmark_return * 100:.2f}%. "
        f"Maximum drawdown over the available period: {max_dd * 100:.2f}%."
    )

    # The JSON must be the final stdout line for the n8n Code node.
    print(json.dumps({"params": params, "text": text}, ensure_ascii=False))


if __name__ == "__main__":
    main()
