-- Daily closing prices, one row per (date, ticker).
CREATE TABLE IF NOT EXISTS prices (
    date    TEXT NOT NULL,           -- ISO date, YYYY-MM-DD
    ticker  TEXT NOT NULL,           -- analysis ticker, e.g. SCOM, SPY, BTC
    close   REAL NOT NULL,           -- adjusted close in the asset's own currency
    source  TEXT NOT NULL,           -- 'yahoo' or 'csv:<filename>'
    loaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker ON prices (ticker, date);

-- Latest date available per ticker (handy for data-freshness checks in n8n).
CREATE VIEW IF NOT EXISTS latest_prices AS
SELECT ticker, MAX(date) AS last_date, COUNT(*) AS n_rows
FROM prices
GROUP BY ticker;
