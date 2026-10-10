# Deribit ETH option trades

`deribit_backfill.py` downloads raw ETH vanilla-option trades from Deribit's public
historical API. It starts at the UTC date three calendar years ago and stops at
the time the command starts. No API key or paid subscription is required.

```bash
python3 -m pip install -r scripts/requirements.txt
python3 scripts/deribit_backfill.py
python3 scripts/deribit_backfill.py --status
```

Each UTC day is a compressed JSON Lines file at
`data/deribit/eth_option_trades/YYYY/MM/DD.jsonl.gz`. A matching `.meta.json`
records the requested time range and trade count. Re-running the script skips
complete days and refreshes a partial final day. Use `--start-date`,
`--end-date` (exclusive), or `--max-days` to limit a run.

The downloaded records contain `mark_price` at execution and `iv` calculated
from the **trade price**. They do not contain historical bid, ask, or a full
hourly option chain. An hourly surface derived from these records must label
unobserved intervals as estimated. The script collects every ETH vanilla-option
trade, including maturities outside the eventual 0DTE to six-month analysis
window, so downstream filters can be changed without redownloading.

Data files are ignored by Git because the full history is large.

## Current hourly quote snapshots and updates

Run `python3 scripts/deribit_update.py` to save the **current** full ETH option
chain (best bid, best ask, mark price and mark IV), convert that hour, and then
refresh any missing trade days through the current time. If the bulk backfill
is already running, the updater saves the snapshot and leaves the existing
backfill alone. Use `--snapshot-only` to collect a quote snapshot without
checking trades.

Snapshots are saved at `data/deribit/eth_option_chain/YYYY/MM/DD/HH.jsonl.gz`.
Running the updater more than once within an hour replaces that hour with the
latest snapshot. Each row has `captured_at_ms`; the filename's hour alone is
not a precise observation timestamp. Run the updater once each hour if you
want a continuous hourly quote series. Missing hours cannot be recovered from
the free historical trade API.

`python3 scripts/deribit_hourly.py --all` converts all downloaded UTC dates to
`data/deribit/eth_option_hourly/YYYY/MM/DD.csv.gz`. The default output covers
0 to 183 days until expiry, approximately six months. Historical trade rows
have empty bid and ask, and `iv_kind=trade_price`; quote snapshot rows have
actual bid/ask and `iv_kind=mark`. The `source` and `observed_at_utc` columns
make the distinction explicit. Prices for these inverse ETH options are in ETH;
IV is in percentage points. An option with no trade in an hour and no saved
snapshot has no row for that hour.
