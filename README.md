# AlphaLab 📈

An educational Indian-stock research sandbox built to grow responsibly.

**v0.1 has one real feature:** a momentum screener working on **synthetic**, fixed-seed
price data. No real stock market prices, orders, recommendations, or actual investment returns.

## Start locally (Windows PowerShell or VS Code terminal)

You need Python 3.11+ (3.12 recommended) and Git.

```powershell
cd alphalab_starter
py -3.12 -m venv .venv
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
2. `screen_momentum()` ranks stocks by trailing return over N available sessions.
3. `app.py` displays a screener table and a sample price chart.
4. Automated tests verify ranking, price validation, stale data filtering and repeatability.

See `docs/architecture.md` and `docs/roadmap.md`.

## Why not download real data automatically?

We want a reproducible offline development workflow first. For any future public or
commercial service, verify market-data licensing and SEBI obligations. Free unofficial
market-data libraries may be intended only for personal research, not redistribution.

## Disclaimer

Research/education software only. No personalized financial advice and no live trading.
