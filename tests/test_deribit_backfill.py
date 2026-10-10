import gzip
import json
import tempfile
import unittest
from pathlib import Path

from scripts.deribit_backfill import collect_interval, download_day


class BackfillTests(unittest.TestCase):
    def test_splits_full_pages_without_losing_boundary_trades(self):
        trades = [
            {"trade_id": "a", "timestamp": 0, "instrument_name": "ETH-X"},
            {"trade_id": "b", "timestamp": 1, "instrument_name": "ETH-X"},
            {"trade_id": "c", "timestamp": 1, "instrument_name": "ETH-X"},
            {"trade_id": "d", "timestamp": 2, "instrument_name": "ETH-X"},
            {"trade_id": "e", "timestamp": 3, "instrument_name": "ETH-X"},
        ]

        def fetch(start, end):
            matches = [trade for trade in trades if start <= trade["timestamp"] <= end]
            return matches[:2], len(matches) > 2

        self.assertEqual(
            [trade["trade_id"] for trade in collect_interval(fetch, 0, 3)],
            ["a", "b", "c", "d", "e"],
        )

    def test_raises_if_one_millisecond_contains_more_than_page_limit(self):
        def fetch(start, end):
            return [{"trade_id": "a", "timestamp": start}], True

        with self.assertRaisesRegex(RuntimeError, "single millisecond"):
            list(collect_interval(fetch, 7, 7))

    def test_day_file_is_resumable_and_keeps_raw_trade_fields(self):
        sample = {
            "trade_id": "ETH-123", "timestamp": 1700000000000,
            "instrument_name": "ETH-24NOV23-1750-P", "price": 0.03,
            "mark_price": 0.031, "iv": 42.5, "index_price": 1800,
        }
        calls = []

        def fetch(start, end):
            calls.append((start, end))
            return [sample], False

        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            first = download_day(output, "2023-11-14", 1699920000000, 1700006399999, fetch)
            second = download_day(output, "2023-11-14", 1699920000000, 1700006399999, fetch)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first, second)
            self.assertEqual(first["trade_count"], 1)
            path = output / "2023" / "11" / "14.jsonl.gz"
            with gzip.open(path, "rt") as stream:
                self.assertEqual(json.loads(stream.readline()), sample)

    def test_partial_day_is_refetched_when_end_time_changes(self):
        calls = []

        def fetch(start, end):
            calls.append((start, end))
            return [], False

        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            download_day(output, "2026-10-10", 0, 5, fetch)
            download_day(output, "2026-10-10", 0, 7, fetch)
            self.assertEqual(calls, [(0, 5), (0, 7)])


if __name__ == "__main__":
    unittest.main()
