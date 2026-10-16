"""Run the full analysis: python run_analysis.py [--prices data/prices.csv] [--rf 0.0]"""
import argparse
from pathlib import Path

import pandas as pd

from analytics import metrics, optimize, plots
from analytics.data import ASSETS, load_prices
from analytics.ingest import YAHOO_SYMBOLS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="data/prices.csv", help="CSV with date + one column per ticker")
    ap.add_argument("--db", help="SQLite database built by analytics.ingest (takes priority over --prices)")
    ap.add_argument("--start", help="only use prices from this date, e.g. 2021-01-01")
    ap.add_argument("--rf", type=float, default=0.0, help="annual risk-free rate, e.g. 0.10")
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)

    simulated = not args.db and not Path(args.prices).exists()
    note = "SIMULATED sample data." if simulated else None
    if simulated:
        print("No prices file found: using SIMULATED sample data (not real markets).")

    if args.db:
        from analytics.data import clean_prices
        from analytics.ingest import read_prices
        prices = clean_prices(read_prices(args.db, start=args.start))
    else:
        prices = load_prices(args.prices)
        if args.start:
            prices = prices.loc[args.start:]
    if args.benchmark not in prices.columns:
        raise SystemExit(f"Benchmark {args.benchmark} not in data columns: {list(prices.columns)}")
    rets = metrics.daily_returns(prices)
    print(f"{rets.shape[1]} assets, {rets.index[0].date()} to {rets.index[-1].date()}, {len(rets)} days")

    # 1. Per-asset statistics
    table = metrics.summary_table(rets, rf=args.rf)
    table.insert(0, "Market", [ASSETS.get(t, "INTL" if t in YAHOO_SYMBOLS else "NSE") for t in table.index])
    table.to_csv(out / "asset_summary.csv")

    # 2. Allocations (long-only, 40% cap)
    w_eq = optimize.equal_weight(rets)
    w_mv = optimize.min_variance(rets)
    w_ms = optimize.max_sharpe(rets, rf=args.rf)
    weights = {"Equal weight": w_eq, "Min variance": w_mv, "Max Sharpe": w_ms}
    pd.DataFrame(weights).to_csv(out / "weights.csv")

    # 3. Portfolio returns with monthly rebalancing
    port = {name: metrics.portfolio_returns(rets, w) for name, w in weights.items()}
    port_df = pd.DataFrame(port)
    port_df[args.benchmark] = rets[args.benchmark]
    port_table = metrics.summary_table(port_df, rf=args.rf)
    port_table.to_csv(out / "portfolio_summary.csv")

    # 4. Charts
    plots.growth_chart(
        {"Max Sharpe": metrics.cumulative_growth(port_df["Max Sharpe"]),
         "Equal weight": metrics.cumulative_growth(port_df["Equal weight"]),
         args.benchmark: metrics.cumulative_growth(port_df[args.benchmark])},
        out / "growth.png", note)
    plots.drawdown_chart(metrics.drawdown_series(port_df["Equal weight"]), out / "drawdown.png",
                         label="Equal-weight portfolio", note=note)
    plots.correlation_heatmap(metrics.correlation_matrix(rets), out / "correlation.png", note)

    mu_cov = lambda w: (  # noqa: E731 - small helper for the frontier markers
        float(w.values @ (rets.mean().values * 252)),
        float((w.values @ (rets.cov().values * 252) @ w.values) ** 0.5))
    marks = {name: tuple(reversed(mu_cov(w))) for name, w in weights.items()}
    plots.frontier_chart(optimize.random_portfolios(rets), optimize.efficient_frontier(rets),
                         marks, out / "frontier.png", note)
    plots.weights_chart(weights, out / "weights.png", note)

    pd.options.display.float_format = "{:.3f}".format
    print("\nPer-asset statistics:\n", table)
    print("\nPortfolio statistics:\n", port_table)
    print("\nWeights:\n", pd.DataFrame(weights))
    print(f"\nOutputs written to {out}/")


if __name__ == "__main__":
    main()
