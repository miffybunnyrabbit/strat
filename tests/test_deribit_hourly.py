import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from scripts.deribit_hourly import convert_day


class HourlyTests(unittest.TestCase):
    def test_historical_trades_have_no_invented_quotes_and_snapshot_overrides_mark(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            trades = base / "trades" / "2026" / "10"
            trades.mkdir(parents=True)
            with gzip.open(trades / "10.jsonl.gz", "wt") as file:
                for row in [
                    {"trade_id": "1", "timestamp": 1791594000000,
                     "instrument_name": "ETH-10OCT26-2500-C", "price": 0.11,
                     "mark_price": 0.12, "iv": 50.0},
                    {"trade_id": "2", "timestamp": 1791594060000,
                     "instrument_name": "ETH-10OCT26-2500-C", "price": 0.12,
                     "mark_price": 0.13, "iv": 51.0},
                    {"trade_id": "3", "timestamp": 1791594060000,
                     "instrument_name": "ETH-17OCT26-2500-P", "price": 0.21,
                     "mark_price": 0.22, "iv": 60.0},
                ]:
                    file.write(json.dumps(row) + "\n")
            chain = base / "chain" / "2026" / "10" / "10"
            chain.mkdir(parents=True)
            with gzip.open(chain / "01.jsonl.gz", "wt") as file:
                file.write(json.dumps({
                    "captured_at_ms": 1791595500000,
                    "instrument_name": "ETH-10OCT26-2500-C",
                    "bid_price": 0.12, "ask_price": 0.14,
                    "mark_price": 0.135, "mark_iv": 52.0,
                }) + "\n")
            output = base / "hourly"
            result = convert_day("2026-10-10", base / "trades", base / "chain", output, 183)
            self.assertEqual(result["row_count"], 2)
            with gzip.open(output / "2026" / "10" / "10.csv.gz", "rt") as file:
                rows = {row["instrument_name"]: row for row in csv.DictReader(file)}
            quoted = rows["ETH-10OCT26-2500-C"]
            self.assertEqual(quoted["bid_price"], "0.12")
            self.assertEqual(quoted["mark_price"], "0.135")
            self.assertEqual(quoted["iv_kind"], "mark")
            self.assertEqual(quoted["trade_count"], "2")
            historical = rows["ETH-17OCT26-2500-P"]
            self.assertEqual(historical["bid_price"], "")
            self.assertEqual(historical["ask_price"], "")
            self.assertEqual(historical["iv_kind"], "trade_price")
            self.assertEqual(historical["iv"], "60.0")

    def test_excludes_expired_and_far_dated_options(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            trades = base / "trades" / "2026" / "10"
            trades.mkdir(parents=True)
            with gzip.open(trades / "10.jsonl.gz", "wt") as file:
                for name in ["ETH-09OCT26-2500-C", "ETH-10OCT26-2500-C",
                             "ETH-25JUN27-2500-C"]:
                    file.write(json.dumps({"trade_id": name, "timestamp": 1791590400000,
                                           "instrument_name": name, "price": 1,
                                           "mark_price": 1, "iv": 50}) + "\n")
            output = base / "hourly"
            result = convert_day("2026-10-10", base / "trades", base / "chain", output, 183)
            self.assertEqual(result["row_count"], 1)
            with gzip.open(output / "2026" / "10" / "10.csv.gz", "rt") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["instrument_name"], "ETH-10OCT26-2500-C")


if __name__ == "__main__":
    unittest.main()
