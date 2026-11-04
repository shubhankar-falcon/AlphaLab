"""Synthetic sample must be stable so comparisons are meaningful."""

import pandas as pd

from alphalab.data.demo import DEMO_TICKERS, DemoPriceProvider


def test_demo_data_is_repeatable():
    first = DemoPriceProvider().get_prices()
    second = DemoPriceProvider().get_prices()
    pd.testing.assert_frame_equal(first, second)
    assert first["ticker"].nunique() == len(DEMO_TICKERS)
    assert first["close"].gt(0).all()
    assert not first.duplicated(["ticker", "date"]).any()
