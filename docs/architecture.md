# AlphaLab architecture — ADR 001 (updated v0.4)

## Principle

Prove one research capability at a time with deterministic data, clear financial
assumptions, and tests that work without the internet.

```text
Streamlit UI
  ├─ app.py: stock screener
  └─ pages/1_Backtesting_Lab.py: backtest
          │
          v
Research logic (no Streamlit and no network calls)
  ├─ strategies/momentum.py: screening
  ├─ backtesting/engine.py: portfolio accounting + rebalance rules
  └─ backtesting/benchmark.py: TRI CSV validation + aligned comparison
          │
          v
PriceDataProvider (date/ticker/positive adjusted close)
  ├─ DemoPriceProvider: fictional reproducible data
  ├─ YahooFinancePriceProvider: personal research (5y for backtests)
  └─ future licensed source

NSE Index Values CSV (user-uploaded, benchmark layer ONLY)
  └─ no remote index fetch, not bundled and not a price-only index substitute
```

## Boundaries

- A strategy cannot fetch prices, place brokerage orders, or write UI state.
- Portfolio logic consumes normalized price history and a configuration object.
- Tests cover selection timing, cost deduction, missing held prices, and metrics.
- No network calls in CI. No accounts, microservices, database or trade execution.
- Current backtests are **not** point-in-time and must be labelled experimental.

See `docs/backtesting_v03.md` for strategy assumptions and
`docs/benchmark_v04.md` for benchmark date alignment and validation rules.
