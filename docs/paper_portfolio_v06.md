# AlphaLab v0.6 — Forward-only Paper Portfolio

## Goal

Move from **research signals** to a saved virtual portfolio, without placing any
real orders or falsely backdating execution. This is an experimental personal
research tool, NOT a broker simulator with realistic market microstructure.

## What happens

1. In v0.5 **Forward Signal Journal**, record a Yahoo-based signal. The saved
   entry includes its actual UTC recording time and its market-data-as-of date.
2. Open **Paper Portfolio**. Select a recorded journal signal and choose
   virtual cash (default ₹100,000) and an estimated buying cost in bps.
3. An immutable, **PENDING** paper plan is saved. This is **not a fill**.
4. Press **Sync completed closes**. Only closes on Indian trading dates **strictly
   after the actual Indian recording date**, and no later than **yesterday in
   India**, can generate hypothetical fills.
5. At the first common eligible completed session, allocate equal target
   amounts from the signal, buy **whole shares** using the Yahoo **raw/unadjusted
   Close**, deduct estimated fees, and retain residual cash.
6. Subsequent Sync actions mark holdings on the **latest common completed**
   raw-close date and calculate NAV and unrealized P&L. Repeated syncs cannot
   create duplicate fills.

The dashboard does **not** auto-update itself in the background. You must click
Sync when you want new observations.

## Why separate price types?

- v0.5 **momentum research:** adjusted historical closes, useful for ranking
  price trends consistently across corporate actions.
- v0.6 **hypothetical purchase:** raw historical Close, closer to a share's
  actual quoted market price on the simulated fill day.

Even raw Close **is not a guaranteed executable price**: orders can experience
spreads, impact and slippage. The initial 10-bps cost is merely a user-configured
estimate and is NOT a full model of Indian taxes, exchange/brokerage fees.

## Important limitations

- No broker integration, market orders, same-session fills, or automatic execution.
- No intraday pricing, partial fills, selling, rebalancing or new cash deposits.
- **Corporate actions are not modeled.** Dividends, splits, spin-offs, and
  delistings can make long-horizon paper P&L materially wrong. Do **not** use
  such P&L as verified out-of-sample performance until addressed.
- Current NSE universe is a current 20-name subset; survivorship bias remains.
- The Yahoo data feed is for personal experimentation, not licensed public or
  commercial redistribution.
- SQLite databases under `.local/` are stored **only on your machine**, not on
  GitHub. Back them up if you want to preserve a real timestamped track record.

## Files

- `pages/3_Paper_Portfolio.py`: Streamlit page
- `src/alphalab/paper/engine.py`: pure, offline-testable SQLite ledger and NAV
- `src/alphalab/paper/market.py`: raw Close data adapter
- `.local/alphalab_signals.sqlite3`: v0.5 journal, read-only in this feature
- `.local/alphalab_paper.sqlite3`: virtual portfolio plans and fill ledger
- `tests/test_paper.py`: offline tests for timing, cash, fees, data validity,
  persistence, idempotency and mark-to-market

## Quality gate

Run these locally before Git commit:

```powershell
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
```

This upgrade adds **no new dependencies** to the existing Python stack.
