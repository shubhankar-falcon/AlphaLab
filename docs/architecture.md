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
Demo provider | Yahoo historical research adapter | licensed vendor later
```

- Strategy functions never request data over the network or place orders.
- Data providers return one normalized schema: `date`, `ticker`, `close`.
- Research data, screener rankings, paper performance, and real execution must remain separate.
- Unit tests exercise business rules without a UI and without network access.
- No API server, microservices, or cloud database until a concrete need emerges.

## Known limitations in v0.2

- Demo mode uses synthetic prices; Yahoo research mode uses historical adjusted closes.
- Demo business-day dates ignore actual NSE holidays.
- Yahoo adjusts for corporate actions but historical universe membership is not preserved.
- No missing-session gap detection beyond requiring the same latest date.
- No portfolio returns, transaction costs, portfolio turnover or look-ahead-proof rebalancing.

Market data from Yahoo is intended for personal use; public market-price display requires
appropriate data licensing. Network data is intentionally outside offline tests.

## Future production concerns

As we add real backtesting: point-in-time universes, adjusted prices and corporate actions,
realistic fill timing, fees/slippage/taxes, benchmark TRI, walk-forward evaluation,
and full strategy/version/data provenance. Live execution is **out of scope**.
