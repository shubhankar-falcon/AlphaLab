# Architecture decisions — ADR 001

## Goal

Prove the end-to-end workflow with a reproducible demo before paying for data or deploying cloud services.

## Boundaries

```
Streamlit UI (app.py)
       |
Strategy functions (src/alphalab/strategies/)
       |
PriceDataProvider interface (src/alphalab/data/provider.py)
       |
Demo provider now -> licensed vendor / broker data provider later
```

- Strategy functions never request data over the network or place orders.
- Data providers return one normalized schema: `date`, `ticker`, `close`.
- Research data, screener rankings, paper performance, and real execution must remain separate.
- Unit tests exercise business rules without a UI and without network access.
- No API server, microservices, or cloud database until a concrete need emerges.

## Known limitations in v0.1

- Synthetic prices; symbol labels are real, but values are entirely fictitious.
- Business-day date series ignores actual NSE exchange holidays.
- No corporate-action adjustment, universe membership history or delisted symbols.
- No missing-session gap detection beyond requiring same latest date.
- No portfolio returns, transaction costs, portfolio turnover or look-ahead-proof rebalancing.

## Future production concerns

As we add real backtesting: point-in-time universes, adjusted prices and corporate actions,
realistic fill timing, fees/slippage/taxes, benchmark TRI, walk-forward evaluation,
and full strategy/version/data provenance. Live execution is **out of scope**.
