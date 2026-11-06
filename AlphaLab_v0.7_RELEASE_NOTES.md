# AlphaLab v0.7 — Risk Intelligence

**Adds a new `Risk Intelligence` page. Keeps existing v0.1–v0.6 functionality and databases unchanged.**

### Added

- Full-historical strategy realized annual volatility, max drawdown and worst day.
- 95% / 99% empirical daily VaR and expected shortfall scaled to the final
  **historical** portfolio NAV (not the active forward paper portfolio).
- Rolling 21/63/126-session annualized volatility chart.
- Risk breakdown of last backtest rebalance's target stocks using 63/126 prior
  trading sessions of adjusted prices (no prices on/after signal's rebalance).
- Two independent static scenarios: parallel stock drop or one-stock drop.
- 23 additional offline unit tests; full reconstructed suite: **100 passed**.

### Data and fidelity limits

No live/broker holdings, no current-paper-portfolio risk, no real-world cash or
margin exposure, no sector classification or market-calibrated VaR. Current-stock
universe is subject to survivorship bias. Scenarios are illustrative static
sensitivities. Research use only; no investment advice.

### Installation into existing project

Extract `AlphaLab_v0.7_update.zip` **into the Git project directory** (the
folder containing `pyproject.toml`), not its parent. Run:

```powershell
Expand-Archive -Path "$HOME\Downloads\AlphaLab_v0.7_update.zip" -DestinationPath . -Force
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
python -m streamlit run app.py
```

Once all checks pass, open the **Risk Intelligence** page in the sidebar and
verify in Demo mode first. Do **not** commit until CI checks are clean.
