# AlphaLab v0.7 — Risk Intelligence

A standalone Streamlit page (`pages/4_Risk_Intelligence.py`) studies historical
risk from the existing momentum backtest. It does **not** mutate the Forward
Signal Journal, Paper Portfolio or any real broker state.

## Measures

- **Annualized volatility:** sample std. dev. of daily *net backtest* returns × √252.
- **Maximum drawdown:** greatest fall from a prior historical NAV peak, including
  initial capital in the first peak.
- **One-day historical VaR (95% / 99%):** empirical lower-tail return quantile,
  expressed as an estimated loss percentage and scaled to **final historical NAV**.
- **Expected shortfall:** average loss in observations at or below that quantile.
  Loss statistics use the entire backtest sample; they are *descriptive*, not
  conditional estimates or maximum loss bounds. 99% requires ≥100 sessions.
- **Rolling volatility:** backward-looking std. dev. of 21, 63 or 126 trading
  sessions, annualized; early incomplete windows remain blank.
- **Target risk estimate:** take the most recent historical rebalance selection,
  then use ONLY the 63/126 sessions of stock returns ending before that rebalance.
  Estimate target-weight portfolio volatility, each stock's standalone volatility,
  and percent contribution to target portfolio variance.
- **Stress scenarios:** separate (a) all-stock parallel drop and (b) single-name
  drop applied to last rebalance's *target* weights and the final backtest NAV.
  These are simplistic sensitivities and not forecasts of real or paper holdings.

## Run

```powershell
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
python -m streamlit run app.py
```

Open **Risk Intelligence** in the sidebar. Demo mode needs no network.
Yahoo mode retrieves retrospectively adjusted research data, for personal use.
No corporate-action handling, live prices, historical constituents, sector
exposures, option Greeks, calibrated stochastic VaR or current paper positions.

## Validation

The new tests cover empirical VaR/ES, drawdown, input data integrity,
pre-rebalance-only covariance, target weight conservation, scenarios and
missing-data failures. All calculations can be tested with synthetic data.
