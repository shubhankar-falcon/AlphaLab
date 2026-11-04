# AlphaLab v0.4 — Correct benchmark comparisons

## Research question

Does the AlphaLab 12–1 momentum strategy outperform the broad Indian equity market **over the identical backtest dates**, after its simulated trading fees?

## Getting Nifty 500 TRI data

1. Visit https://www.niftyindices.com/reports/historical-data.
2. Choose **Total returns Index Values** (not **Historical Index Data**, which contains the *price index*).
3. Select **NIFTY 500**, and select a date range that fully covers your simulated strategy dates (the Yahoo 5-year setting can yield ~4 years of backtest equity after the 252-session formation window).
4. Use the site's **CSV format** export. If the site requires shorter date windows, export multiple CSV files and select them together in AlphaLab.
5. Go to the **Backtesting Lab** page, switch to **Yahoo (historical)**, then upload the downloaded files in the sidebar.

### CSV fields

Recognized headers include `IndexName`, `Date`, `TotalReturnsIndex` (or `Index Name`, `Date`, `Total Returns Index`). `Net Total Return Index` and `Close` are **not** substituted for gross TRI. This program does not download or redistribute NSE TRI values itself.

### Calculation

- Benchmarks and strategy are compared on **the same strategy dates** and normalized to the same initial capital.
- Benchmark total return = end benchmark NAV / starting capital − 1.
- Excess total return in percentage points = strategy total return (%) − benchmark total return (%). **This is not regression alpha.**
- Annualized comparison uses 252 observed trading sessions per year, consistent with v0.3.
- Portfolio has simulated per-trade fees; index returns are theoretical, before investor fees, tracking difference, taxes, and ETF transaction costs.
- Dates outside the CSV history are **never extrapolated**. At least 98% of strategy dates must have observed TRI values; small interior calendar mismatches are forward-filled using the last observed TRI level. This is stated on the UI.

### Known limitations

- **Huge:** Current stocks only, survivorship bias, not actual historical Nifty 500 universe.
- Adjusted prices from Yahoo, not licensed exchange production feeds.
- Simplified close execution. No realistic tax/impact/delisting/IPO/corporate-action model.
- No genuine out-of-sample validation or inference of statistically significant alpha.
- Benchmark uploaded from user files; the tool verifies index-name header when present, but cannot authenticate a file's origin.
- Demo mode shows a **synthetic daily-rebalanced equal-weight proxy** from fictional demo stock series. It is NOT Nifty 500 TRI.

## Next after v0.4

Review real benchmark outcome, then add strategy validation (historical constituents, slippage sensitivity, holdout periods) before making performance claims.
