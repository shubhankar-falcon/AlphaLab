# AlphaLab v0.5 — Forward Signal Journal

Drop-in update for your existing v0.4 Git repository. It **only adds files**;
existing stock screener, backtesting page, benchmark, local fixes and Git history
are left unchanged.

### Files
- `pages/2_Forward_Signal_Journal.py` — Streamlit research journal UI.
- `src/alphalab/research/signals.py` — pure point-in-time momentum signal generator.
- `src/alphalab/research/store.py` — append-only-ish SQLite snapshot persistence.
- `tests/test_signal_journal.py` — offline quality tests.
- `docs/signal_journal_v05.md` — design choices and limitations.

### Run (existing .venv)

```powershell
python -m ruff format .
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
python -m streamlit run app.py
```

Open **Forward Signal Journal** in Streamlit's page navigation. By default,
selects Yahoo and shows signal candidates from real historical closes.
Click **Record this research signal** to save an immutable timestamped entry.
This is NOT paper execution or live trading.
