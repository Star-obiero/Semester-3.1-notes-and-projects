"""Price ingestion into SQLite.

Sources
- International assets: Yahoo Finance via the `yfinance` package.
- NSE (Kenya) stocks: CSV files in a folder, one file per ticker (SCOM.csv, EQTY.csv, ...).
  Free, reliable NSE price APIs are scarce, so this accepts exports from whichever
  source you trust (broker statement, NSE data, Investing.com export, etc.).
  Check each series for splits and dividends: use adjusted prices where you can.

CLI
    python -m analytics.ingest --db data/portfolio.db --yahoo --nse-dir data/nse
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"

# analysis ticker -> Yahoo symbol
YAHOO_SYMBOLS = {"SPY": "SPY", "GLD": "GLD", "BTC": "BTC-USD"}

# Column names accepted in CSV exports, in order of preference.
_DATE_COLS = ("date", "Date", "DATE", "Trade Date")
_PRICE_COLS = ("adj close", "Adj Close", "close", "Close", "CLOSE", "Price", "price", "Closing Price")


def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA.read_text())
    return con


def upsert_prices(con: sqlite3.Connection, long_df: pd.DataFrame, source: str) -> int:
    """long_df has columns date (datetime), ticker, close. Existing rows are replaced."""
    df = long_df.dropna(subset=["close"]).copy()
    df = df[df["close"] > 0]
    rows = [(d.strftime("%Y-%m-%d"), t, float(c), source)
            for d, t, c in zip(df["date"], df["ticker"], df["close"])]
    with con:
        con.executemany(
            "INSERT INTO prices (date, ticker, close, source) VALUES (?,?,?,?) "
            "ON CONFLICT(date, ticker) DO UPDATE SET close=excluded.close, "
            "source=excluded.source, loaded_at=datetime('now')",
            rows,
        )
    return len(rows)


def _to_long(wide: pd.DataFrame) -> pd.DataFrame:
    wide = wide.copy()
    wide.index.name = "date"
    out = wide.reset_index().melt(id_vars="date", var_name="ticker", value_name="close")
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return out


# ---------------------------------------------------------------- Yahoo

def fetch_yahoo(symbols: dict[str, str] | None = None, start: str = "2018-01-01") -> pd.DataFrame:
    """Return a wide DataFrame of adjusted closes keyed by analysis ticker."""
    import yfinance as yf  # imported here so the rest of the module works without it

    symbols = symbols or YAHOO_SYMBOLS
    raw = yf.download(list(symbols.values()), start=start, auto_adjust=True,
                      progress=False, group_by="column")
    close = raw["Close"]
    if isinstance(close, pd.Series):          # single symbol edge case
        close = close.to_frame(next(iter(symbols.values())))
    inverse = {v: k for k, v in symbols.items()}
    close = close.rename(columns=inverse)
    missing = [t for t in symbols if t not in close.columns or close[t].dropna().empty]
    if missing:
        print(f"WARNING: no Yahoo data returned for {missing}")
    return close.dropna(how="all")


# ---------------------------------------------------------------- NSE CSV

def read_price_csv(path: Path) -> pd.Series:
    """Parse one CSV into a date-indexed close series. Tolerates thousands separators."""
    df = pd.read_csv(path)
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    price_col = next((c for c in _PRICE_COLS if c in df.columns), None)
    if date_col is None or price_col is None:
        raise ValueError(f"{path.name}: need a date column {_DATE_COLS[:2]} and a price column "
                         f"{_PRICE_COLS[:4]}; found {list(df.columns)}")
    s = pd.Series(
        pd.to_numeric(df[price_col].astype(str).str.replace(",", ""), errors="coerce").values,
        index=pd.to_datetime(df[date_col], errors="coerce", dayfirst=False),
    )
    s = s[s.index.notna()].sort_index()
    return s[~s.index.duplicated(keep="last")]


def import_nse_csvs(folder: str | Path) -> pd.DataFrame:
    """Each file name (without extension) is the ticker."""
    series = {}
    for p in sorted(Path(folder).glob("*.csv")):
        try:
            series[p.stem.upper()] = read_price_csv(p)
        except ValueError as e:          # one bad file should not drop the others
            print(f"WARNING: skipped {p.name}: {e}")
    if not series:
        raise FileNotFoundError(f"No usable CSV files found in {folder}")
    return pd.DataFrame(series)


# ---------------------------------------------------------------- read back

def read_prices(db_path: str | Path, tickers: list[str] | None = None,
                start: str | None = None) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    q = "SELECT date, ticker, close FROM prices"
    clauses, params = [], []
    if tickers:
        clauses.append(f"ticker IN ({','.join('?' * len(tickers))})")
        params += tickers
    if start:
        clauses.append("date >= ?")
        params.append(start)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    df = pd.read_sql_query(q, con, params=params, parse_dates=["date"])
    con.close()
    if df.empty:
        raise ValueError("No prices in database. Run ingestion first.")
    return df.pivot(index="date", columns="ticker", values="close").sort_index()


def main():
    ap = argparse.ArgumentParser(description="Load prices into SQLite")
    ap.add_argument("--db", default="data/portfolio.db")
    ap.add_argument("--yahoo", action="store_true", help="fetch international assets from Yahoo Finance")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--nse-dir", help="folder of NSE CSV files, one per ticker")
    args = ap.parse_args()

    con = connect(args.db)
    if args.yahoo:
        n = upsert_prices(con, _to_long(fetch_yahoo(start=args.start)), "yahoo")
        print(f"Yahoo: {n} rows upserted")
    if args.nse_dir:
        try:
            n = upsert_prices(con, _to_long(import_nse_csvs(args.nse_dir)), "csv")
            print(f"NSE CSV: {n} rows upserted")
        except FileNotFoundError as e:   # warn, don't crash: the summary flags missing NSE data
            print(f"WARNING: no NSE data loaded ({e}). The weekly summary will say NSE has no data.")
    for row in con.execute("SELECT ticker, last_date, n_rows FROM latest_prices ORDER BY ticker"):
        print(f"  {row[0]:6s} last={row[1]}  rows={row[2]}")
    con.close()


if __name__ == "__main__":
    main()
