# AlphaLab v0.3 — Backtesting research methodology

The **12–1 cross-sectional momentum** experiment is educational research.
It follows the idea of ranking by approximately 12-month past returns while
omitting the most recent month. This is a **long-only equal-weight variant**, not
an exact academic zero-cost long-short factor portfolio or a hedge fund model.

## Timing and eligibility

- Daily input: `date,ticker,close` with strictly positive, adjusted daily closes.
- Each calendar month, place orders on its first **observed trading session**.
- Selection on session `t` uses price at `t-1-21` divided by price at `t-1-252`.
  Neither the selection score nor candidate ranking looks at prices from `t` onward.
- Positions are sized using the **session t close**; first exposure is from `t` to `t+1`.
  Real execution at that closing price is **not guaranteed**. Simulated fill is idealized.
- Each candidate must have all required historical closing observations and a
  closing price on trade date. IPOs do not get fabricated past data.
- We mark existing shares to market daily; portfolio weights drift until rebalancing.
  An absent price for a held stock causes a failure; it is never filled with zero return.
- New buys and sells incur a cost in basis points (bps) on **both** sides.
  Cost payments reduce investable NAV and are solved into position sizing.

## Metrics

- Total return: `(ending NAV / starting NAV) - 1`.
- CAGR: `(ending NAV / starting NAV) ^ (252 / n_sessions) - 1`.
- Drawdown: portfolio NAV divided by its running high-water mark (including
  starting capital), minus 1.
- Annualized volatility: standard deviation of daily portfolio returns × sqrt(252).
- Annualized Sharpe: average daily return / daily standard deviation × sqrt(252).
  Risk-free rate **assumed to be 0%**. When volatility is zero, display N/A.
- Gross turnover: absolute dollar purchases **plus** absolute dollar sales,
  divided by pre-trade portfolio NAV. This is **not** the half-sum turnover convention.

## Non-negotiable limitations

1. **Survivorship bias:** v0.3 backtests today's ~20-stock sample over earlier years.
   Delisted companies and past universe members are missing. The results must not
   be presented as representative Nifty 500 historical performance.
2. **Corporate actions:** yfinance adjusted closes can be retrospectively revised;
   corporate-action handling is not point-in-time. Changes after stock demergers
   may require explicit review.
3. **Execution and costs:** assumed daily close fill, simplified constant costs;
   no market impact, liquidity, broker fees by slab, GST, STT, tax, slippage
   distributions, position-size limits or borrow costs.
4. **Benchmark:** no Nifty 500 total return index (TRI) series included here.
   Comparison to a price-only index would be misleading.
5. **Overfitting:** this is an in-sample prototype. No walk-forward, out-of-sample,
   factor attribution, stress tests, or robustness grid.
6. **Data:** Yahoo Finance is useful for **personal research** but not a licensed
   production redistributable data feed. Do not publish downloaded price histories.

Next upgrades: point-in-time universe, licensed data, official benchmark TRI,
robust execution model, and out-of-sample testing.
