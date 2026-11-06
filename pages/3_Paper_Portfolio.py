"""AlphaLab v0.6: intentionally conservative, forward-only paper portfolio."""

from pathlib import Path

import pandas as pd
import streamlit as st

from alphalab.data.yahoo import MarketDataError
from alphalab.paper import (
    create_paper_account,
    list_paper_accounts,
    mark_paper_account,
    paper_trades_to_csv,
    settle_pending_paper_account,
)
from alphalab.paper.market import fetch_yahoo_raw_closes
from alphalab.research import load_snapshots

st.set_page_config(page_title="AlphaLab | Paper Portfolio", page_icon="🧾", layout="wide")
JOURNAL_PATH = Path(".local") / "alphalab_signals.sqlite3"
PAPER_PATH = Path(".local") / "alphalab_paper.sqlite3"


@st.cache_data(ttl=900, show_spinner=False)
def market_prices(tickers: tuple[str, ...]) -> pd.DataFrame:
    return fetch_yahoo_raw_closes(tickers)


st.title("🧾 AlphaLab — Paper Portfolio")
st.caption("v0.6 · Forward-only virtual capital · No brokerage orders or real money")
st.info(
    "Only a signal that was actually saved in the v0.5 journal can create a paper plan. "
    "Orders remain pending until a **later completed trading session**. "
    "We do not pretend that historical closes were executable at recording time."
)

signals = load_snapshots(JOURNAL_PATH, source="yahoo")
if not signals:
    st.warning(
        "No Yahoo research signals recorded yet. Open Forward Signal Journal, "
        "select Yahoo data, and record a signal first."
    )
else:
    st.subheader("Start a simulated ₹1 lakh portfolio")
    signal_ids = [s["id"] for s in signals]
    signal_map = {s["id"]: s for s in signals}
    selected_id = st.selectbox(
        "Choose a previously recorded signal",
        signal_ids,
        format_func=lambda i: (
            f"Signal #{i} · recorded {signal_map[i]['created_at_utc']} UTC · "
            f"market as-of {signal_map[i]['asof_date']}"
        ),
    )
    with st.form("create_paper_plan"):
        starting_cash = st.number_input(
            "Starting paper cash (₹)",
            min_value=5_000.0,
            max_value=10_000_000.0,
            value=100_000.0,
            step=5_000.0,
        )
        bps = st.number_input(
            "Estimated cost per buy (bps)",
            min_value=0.0,
            max_value=1000.0,
            value=10.0,
            step=5.0,
        )
        submitted = st.form_submit_button("Create pending paper orders", type="primary")
    if submitted:
        try:
            account_id, created = create_paper_account(
                PAPER_PATH,
                signal_map[selected_id],
                initial_cash=float(starting_cash),
                cost_bps=float(bps),
            )
        except ValueError as exc:
            st.error(f"Cannot create paper portfolio: {exc}")
        else:
            if created:
                st.success(f"Created paper portfolio #{account_id}. Orders are pending.")
            else:
                st.info(f"Portfolio #{account_id} already exists; no duplicate orders created.")

accounts = list_paper_accounts(PAPER_PATH)
if st.session_state.pop("paper_sync_success", False):
    st.success("Completed market data checked; paper portfolio register updated.")
st.subheader("Portfolio register")
if not accounts:
    st.info("No paper portfolios yet. Record and select a Yahoo signal above.")
    st.stop()

rows = [
    {
        "Portfolio": a["id"],
        "Signal": a["journal_signal_id"],
        "Recorded (UTC)": a["signal_recorded_utc"],
        "Status": a["status"].upper(),
        "Fill date": a["fill_date"] or "—",
        "Starting cash (₹)": a["initial_cash"],
        "Unallocated cash (₹)": a["cash_after"],
    }
    for a in accounts
]
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

account_map = {a["id"]: a for a in accounts}
account_id = st.selectbox("Inspect paper portfolio", list(account_map))
account = account_map[account_id]
if account["status"] == "pending":
    st.warning(
        "PENDING: A paper fill requires a completed trading date strictly after the signal's "
        "actual recording date in India. On weekends or holidays, this can take several days."
    )
    st.dataframe(pd.DataFrame(account["signal"]["picks"]), hide_index=True)
else:
    st.success(f"Simulated initial purchases dated {account['fill_date']}.")
    st.dataframe(pd.DataFrame(account["fills"]), use_container_width=True, hide_index=True)
    st.download_button(
        "Export simulated fills CSV",
        data=paper_trades_to_csv(account),
        file_name=f"alphalab_paper_{account_id}.csv",
        mime="text/csv",
    )

if st.button("Sync completed closes and update paper portfolios"):
    symbols = tuple(
        sorted(
            {
                f["ticker"]
                for a in accounts
                for f in (a["fills"] if a["status"] == "active" else a["signal"]["picks"])
            }
        )
    )
    market_prices.clear()
    try:
        raw_prices = market_prices(symbols)
        for a in accounts:
            if a["status"] == "pending":
                settle_pending_paper_account(PAPER_PATH, a["id"], raw_prices)
        st.session_state["paper_marks"] = raw_prices
        st.session_state["paper_sync_success"] = True
        accounts = list_paper_accounts(PAPER_PATH)
        account_map = {a["id"]: a for a in accounts}
        account = account_map[account_id]
        st.rerun()
    except (ValueError, MarketDataError) as exc:
        st.error(f"Paper sync failed safely: {exc}")

if account["status"] == "active":
    raw_prices = st.session_state.get("paper_marks")
    if raw_prices is None:
        st.info("Click Sync completed closes to calculate the latest paper P&L.")
    else:
        try:
            valuation = mark_paper_account(account, raw_prices)
        except ValueError as exc:
            st.warning(f"Current portfolio cannot be valued reliably: {exc}")
        else:
            st.caption(f"Valued using common raw closes on {valuation['mark_date']}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Paper portfolio NAV", f"₹{valuation['nav_inr']:,.2f}")
            c2.metric("Net paper P&L", f"₹{valuation['pnl_inr']:,.2f}")
            c3.metric("Paper return", f"{valuation['return_pct']:+.2f}%")
            c4.metric("Cash remaining", f"₹{valuation['cash_inr']:,.2f}")
            st.dataframe(
                pd.DataFrame(valuation["holdings"]),
                use_container_width=True,
                hide_index=True,
            )

st.warning(
    "RESEARCH LIMITATIONS: Fills are hypothetical at the next *completed* session's Yahoo "
    "unadjusted close, not guaranteed executable prices. Estimated costs omit full Indian "
    "brokerage/taxes, actual spreads and slippage. Dividends, splits, delistings and other "
    "corporate actions are not accounted for; P&L can be misleading across such events. "
    "There is no automated scheduling, real-time trading or investment advice. "
    "SQLite data lives only on this computer; back up .local/ regularly."
)
