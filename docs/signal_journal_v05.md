# AlphaLab v0.5 — Forward Signal Journal

## Purpose

The Backtesting Lab tells us how a rules-based strategy **might have performed** over
historical price data. The new Signal Journal persists **what our strategy says today**
(and when we really recorded it), instead of re-creating and revising past decisions.

## How it works

- Pulls Yahoo daily adjusted-price history, or uses clearly labelled demo data.
- Ignores the current Indian calendar day's bar to avoid unfinished daily candles.
- Applies the same 12–1 momentum formation rule: from `t - 252` through `t - 21`
  observed sessions. Requires uninterrupted price coverage through `t`.
- Saves top-N selections, weights, source, formation dates, and a price-input SHA256.
- Persists signals in SQLite at `.local/alphalab_signals.sqlite3`, ignored by Git.
- Keeps the **first** snapshot for a given observed date/source/settings/universe;
  revised vendor prices do not silently replace the initial research decision.
- Exports a CSV including both the actual **recorded UTC time** and historical
  **price-as-of date**. Signals with old as-of dates are not live history.

## Data custody

The DB lives on your machine, NOT GitHub. Back it up if you want to keep your
recorded research track record. The current version has no login/accounts.

## What this does **not** do

It does not execute trades, simulate fills, report portfolio returns, or establish
forward performance. Next version should introduce a realistic paper-order ledger
and explicit next-session fill assumption. Before a public or commercial launch,
we need correctly licensed data and index membership history.

## Test

`python -m pytest -v` and `python -m ruff check .` before committing.
