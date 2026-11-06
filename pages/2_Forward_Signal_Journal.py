"""AlphaLab v0.5: date-stamped, immutable research decisions (no trading)."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from alphalab.data.demo import DemoPriceProvider
from alphalab.data.yahoo import MarketDataError, YahooFinancePriceProvider
from alphalab.research import (
    build_momentum_snapshot,
    load_snapshots,
    save_snapshot,
    snapshots_to_csv,
)

st.set_page_config(page_title="AlphaLab | Signal Journal", page_icon="📓", layout="wide")
DB_PATH = Path(".local") / "alphalab_signals.sqlite3"


@st.cache_data(show_spinner=False)
def demo_prices() -> pd.DataFrame:
    return DemoPriceProvider().get_prices()


@st.cache_data(ttl=3600, show_spinner=False)
def historical_prices() -> pd.DataFrame:
    return YahooFinancePriceProvider(period="5y").get_prices()


st.title("📓 AlphaLab — Forward Signal Journal")
st.caption("v0.5 · Record research decisions before outcomes · No brokers or real orders")
st.info(
    "Unlike a backtest, each saved signal has an actual recording timestamp and will not "
    "be silently overwritten. This is a research journal, NOT a live performance record."
)
with st.sidebar:
    st.header("Journal settings")
    source_label = st.radio("Data", ["Yahoo (real historical)", "Demo (synthetic)"], index=0)
    top_n = st.slider("Top stocks", min_value=2, max_value=10, value=5)
    lookback = st.selectbox("Lookback (sessions)", [126, 252], index=1)
    skip = st.selectbox("Skip recent (sessions)", [21, 42], index=0)
    if st.button("Refresh Yahoo historical prices"):
        historical_prices.clear()

source = "yahoo" if source_label.startswith("Yahoo") else "synthetic_demo"
# Even if Yahoo provides an unfinished intraday bar, this page only uses
# closes strictly before the current Indian calendar day.
today_india = datetime.now(ZoneInfo("Asia/Kolkata")).date()
cutoff = today_india - timedelta(days=1) if source == "yahoo" else None
try:
    prices = historical_prices() if source == "yahoo" else demo_prices()
    snapshot = build_momentum_snapshot(
        prices,
        source=source,
        lookback_sessions=lookback,
        skip_sessions=skip,
        top_n=top_n,
        cutoff_date=cutoff,
    )
except (ValueError, MarketDataError) as exc:
    st.error(f"Unable to generate signal: {exc}")
    st.stop()

left, right, last = st.columns(3)
left.metric("Observed market close", snapshot["asof_date"])
right.metric("Eligible selection", len(snapshot["picks"]))
last.metric("Strategy", f"{lookback}–{skip} momentum")
st.caption(
    f"Formation: {snapshot['formation_start']} → {snapshot['formation_end']}. "
    "Signal is based on adjusted closes, and is NOT a filled trade or an investment recommendation."
)
st.subheader("Current calculated selection")
st.dataframe(pd.DataFrame(snapshot["picks"]), use_container_width=True, hide_index=True)
st.caption(f"Input fingerprint: `{snapshot['prices_sha256'][:16]}` · Source: {source}")

if st.button("Record this research signal", type="primary"):
    record_id, created = save_snapshot(DB_PATH, snapshot)
    if created:
        st.success(f"Saved signal #{record_id} with its UTC recording time.")
    else:
        st.info(f"Signal #{record_id} already saved for this date and settings; original retained.")

st.subheader("Research decision history")
records = load_snapshots(DB_PATH, source=source)
if not records:
    st.info("No saved signals yet. Click ‘Record this research signal’ above.")
else:
    table = pd.DataFrame(
        [
            {
                "ID": r["id"],
                "Recorded (UTC)": r["created_at_utc"],
                "Market data as-of": r["asof_date"],
                "Strategy": f"{r['lookback_sessions']}–{r['skip_sessions']}",
                "Stocks": ", ".join(x["ticker"] for x in r["picks"]),
            }
            for r in records
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.download_button(
        "Export research journal CSV",
        data=snapshots_to_csv(records),
        file_name=f"alphalab_signals_{source}.csv",
        mime="text/csv",
    )
    with st.expander("Recorded signals and integrity hashes"):
        for r in records[:10]:
            st.write(
                f"#{r['id']} · recorded {r['created_at_utc']} · "
                f"market data {r['asof_date']} · input hash `{r['prices_sha256']}`"
            )

st.warning(
    "REALISM LIMITS: Yahoo may revise historical adjusted prices. Data is not licensed for "
    "commercial redistribution. Current ticker list has survivorship bias. No executions, "
    "slippage, brokerage, fills, P&L, or real-time automation are included yet. "
    "Signals saved today must not be described as if they existed on historical observation dates."
)
