# AlphaLab 📈

An educational Indian-stock research sandbox built to grow responsibly.

**v0.2 adds an opt-in Yahoo Finance historical-price provider** alongside the existing
reproducible synthetic demo. There is no live trading, order placement, backtesting,
or investment recommendation engine.

## Start locally (Windows PowerShell or VS Code terminal)

You need Python 3.11+ (Python 3.13 also works) and Git.

```powershell
cd alphalab_starter
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m streamlit run app.py
```

If `py -3.12` is unavailable but `python --version` reports 3.11+, use:

```powershell
python -m venv .venv
```

If PowerShell blocks script activation, either switch VS Code's terminal to Command Prompt
and run `.venv\Scripts\activate.bat`, or run tools directly as:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit displays a local URL, usually `http://localhost:8501`.

## Verify quality

```powershell
python -m pytest -q
ruff check .
ruff format --check .
```

For your first Git commit:

```powershell
git init
git add .
git commit -m "chore: bootstrap AlphaLab research sandbox"
```

## How it works

1. `DemoPriceProvider` generates deterministic **fake** daily prices for 20 labelled NSE stocks.
2. `YahooFinancePriceProvider` downloads historical split/dividend-adjusted daily closes
   for the same symbol list in **personal research** mode; there is no live feed.
3. `screen_momentum()` ranks stocks by trailing return over N available sessions.
4. `app.py` exposes a data-source selector, a screener, and a price chart.
5. Offline tests verify ranking and data-provider normalization without contacting Yahoo.

See `docs/architecture.md` and `docs/roadmap.md`.

## Market data, reliability, and licensing

- **Demo** is the default and works completely offline.
- **Yahoo (historical)** is opt-in, requires internet, and may omit symbols or return errors.
- Prices are adjusted for splits and dividends, so they are suitable for comparing
  historical returns but may not match historical exchange-traded closing prices.
- Data is cached for one hour to reduce unnecessary requests. A Refresh button clears it.
- Free Yahoo data accessed by `yfinance` is intended for **personal use only**.
  Do not redistribute downloaded market data or launch a public-facing commercial
  dashboard using this feed without appropriate data rights.
- An official licensed broker/exchange data source can be substituted behind the
  existing provider interface in a future version.
- Strategy outputs are not recommendations or verified trading performance.

## Disclaimer

Research/education software only. No personalized financial advice and no live trading.
