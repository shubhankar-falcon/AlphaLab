"""A small interface so we can change data sources without changing strategies."""

from typing import Protocol

import pandas as pd


class PriceDataProvider(Protocol):
    def get_prices(self) -> pd.DataFrame:
        """Return rows with columns: date, ticker, close (positive adjusted prices)."""
        ...
