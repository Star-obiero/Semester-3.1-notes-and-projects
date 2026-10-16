"""Build the weekly summary used by the n8n WhatsApp step.

Prints ONE line of JSON to stdout:
    {"period": ..., "params": [7 single-line strings], "text": "...", "stale": bool}

`params` fill the variables of the approved WhatsApp template (see n8n/WHATSAPP_SETUP.md).
WhatsApp template variables must not contain line breaks, so everything here is one line.

    python -m analytics.weekly_summary --db data/portfolio.db --benchmark SPY
"""
import argparse
import json
from datetime import date

import pandas as pd

from analytics import metrics
from analytics.data import ASSETS, clean_prices
from analytics.ingest import YAHOO_SYMBOLS, read_prices

WEEK_DAYS = 5          # trading rows that make up "this week"
STALE_AFTER_DAYS = 4   # warn if the newest common price date is older than this


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def build_summary(prices: pd.DataFrame, benchmark: str = "SPY", today: date | None = None) -> dict:
    today = today or date.today()
    rets = metrics.daily_returns(prices)
    if len(rets) <= WEEK_DAYS:
        raise ValueError("Not enough history for a weekly summary")

    week = rets.iloc[-WEEK_DAYS:]
    weekly = (1 + week).prod() - 1                       # per-asset weekly return
    eq = pd.Series(1 / rets.shape[1], index=rets.columns)
    port = metrics.portfolio_returns(rets, eq)           # equal weight, monthly rebalance
    port_week = (1 + port.iloc[-WEEK_DAYS:]).prod() - 1
    dd_now = metrics.drawdown_series(port).iloc[-1]

    best, worst = weekly.idxmax(), weekly.idxmin()
    bench_week = weekly[benchmark] if benchmark in weekly.index else float("nan")

    last = rets.index[-1].date()
    age = (today - last).days
    stale = age > STALE_AFTER_DAYS
    freshness = f"STALE, last common price date {last}" if stale else f"{last}"

    period = f"{week.index[0].date()} to {last}"
    params = [
        period,
        pct(port_week),
        f"{benchmark} {pct(bench_week)}" if pd.notna(bench_week) else "n/a",
        f"{best} {pct(weekly[best])}",
        f"{worst} {pct(weekly[worst])}",
        f"{abs(dd_now) * 100:.1f}% below peak" if dd_now < -0.0005 else "at a new high",
        freshness,
    ]
    params = [" ".join(p.split()) for p in params]       # collapse any whitespace/newlines

    def fmt(tickers):
        ordered = weekly[tickers].sort_values(ascending=False)
        return ", ".join(f"{t} {pct(v)}" for t, v in ordered.items())

    # Anything not fetched from Yahoo comes from the NSE CSV folder, so new NSE tickers
    # (e.g. TOTL) are picked up without editing a ticker list.
    intl = [t for t in weekly.index if t in YAHOO_SYMBOLS]
    nse = [t for t in weekly.index if t not in YAHOO_SYMBOLS]
    missing_nse = [t for t, m in ASSETS.items() if m == "NSE" and t not in weekly.index]

    if nse:
        nse_line = f"NSE (avg {pct(weekly[nse].mean())}): {fmt(nse)}"
        if missing_nse:
            nse_line += f". Missing: {', '.join(missing_nse)}"
    else:
        nse_line = "NSE: NO DATA. Add CSVs to data/nse and re-run the ingest step"
    intl_line = f"International: {fmt(intl)}" if intl else "International: no data"

    text = "\n".join([
        f"Weekly portfolio summary ({period})",
        f"Equal-weight portfolio ({len(weekly)} assets): {pct(port_week)} | benchmark {params[2]}",
        f"Drawdown: {params[5]}",
        nse_line,
        intl_line,
        f"Data updated: {freshness}",
        "Historical figures only, not a forecast or investment advice.",
    ])
    coverage = {"nse": nse, "international": intl, "missing_nse": missing_nse}
    return {"period": period, "params": params, "text": text, "stale": stale, "coverage": coverage}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/portfolio.db")
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    prices = clean_prices(read_prices(args.db))
    today = date.fromisoformat(args.today) if args.today else None
    print(json.dumps(build_summary(prices, args.benchmark, today), ensure_ascii=False))


if __name__ == "__main__":
    main()
