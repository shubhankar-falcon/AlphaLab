# AlphaLab 📈

An educational Indian-equities quant research lab. It is designed around a
reproducible demo, modular data feeds, independently testable financial logic,
and CI quality gates.

**v0.4 adds an optional Nifty 500 TRI benchmark comparison to the v0.3
monthly 12–1 momentum backtest, while preserving the existing screener.**
The main v0.2 stock screener is preserved, including both synthetic and real
historical-data modes. There is no brokerage integration or live trading.

## Run locally (Windows PowerShell / VS Code)

Use Python 3.11+ (Python 3.13 works).

```powershell
cd alphalab_starter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m streamlit run app.py
```

For the first installation, follow the setup above. For future updates to the
same repository, **do not recreate** `.venv`: activate the existing environment,
then run `python -m pip install -e ".[dev]"` if dependencies changed.

Open the **Backtesting Lab** page from Streamlit's page navigation on the left.
The main page remains the stock screener.

### Validate before committing

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
```

## Project structure

- `app.py` — v0.2 stock screener, the home page.
- `pages/1_Backtesting_Lab.py` — v0.4 backtest and benchmark comparison page.
- `src/alphalab/data/` — reproducible demo and Yahoo historical-data adapters.
- `src/alphalab/strategies/` — stock screening.
- `src/alphalab/backtesting/engine.py` — reusable backtest engine.
- `src/alphalab/backtesting/benchmark.py` — TRI CSV parsing and matched-date comparison.
- `tests/` — fully offline automated unit tests.
- `.github/workflows/ci.yml` — checks formatting, lint and tests on GitHub.
- `docs/backtesting_v03.md` — original backtest methodology and assumptions.
- `docs/benchmark_v04.md` — benchmark CSV format, validation and method.

## What the first backtest means

Monthly, at an observed trading session `t`, rank stocks using adjusted price
returns from `t-1-252` to `t-1-21` sessions (12–1 momentum). Allocate equally
to the highest-ranked stocks at the session `t` adjusted close, simulate share
holdings and subtract a flat transaction-cost estimate from both purchases and
sales. Selections are based on *prior-day* data: trade-day price changes cannot
influence the picks.

Displays portfolio value, total return, CAGR, annual volatility, Sharpe ratio
(assuming 0% risk-free rate), maximum drawdown, monthly trades, fees, and
selection history. Synthetic demo mode requires no internet; real historic
Yahoo mode requests up to 5 years of daily data.

**Do not treat these results as audited or investable strategy performance:**
- The model uses a **current 20-name sample**, not a point-in-time historical
  Nifty 500 universe. This creates substantial survivorship/selection bias.
- Closing-price execution is idealized; the data uses retrospectively adjusted
  closes. The cost approximation omits Indian statutory taxes, broker fees,
  actual bid-ask spreads, and real slippage.
- Official Nifty 500 **total return** comparison requires a user-provided NSE
  CSV. No index return series is bundled, invented, or fetched automatically.
- No walk-forward or out-of-sample validation has been done.
- Yahoo market data via `yfinance` is for **personal research**; do not
  redistribute it as a public/commercial price-data service without a licence.

For the complete calculation specification, see `docs/backtesting_v03.md`.

## Disclaimer

Education and personal market research only. Nothing in AlphaLab is trading
advice, a prediction, or a system for accepting money or placing orders.


## v0.4 — Benchmark comparison

Backtesting Lab now supports a synthetic equal-weight **demo market proxy** and
user-uploaded **official Nifty 500 Total Returns Index (TRI)** daily CSV(s) in
Yahoo historical mode. Real benchmark comparisons are never manufactured from
price-only indexes. Both series are normalized to the same starting capital and
dates; return differences are descriptive, **not** proof of alpha.

See [benchmark_v04.md](docs/benchmark_v04.md) for NSE CSV download steps,
limitations and calculation details.
