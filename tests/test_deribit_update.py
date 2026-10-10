import gzip
import json
import tempfile
import unittest
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.deribit_update import save_chain_snapshot


class SnapshotTests(unittest.TestCase):
    def test_script_runs_from_repo_root(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "deribit_update.py"
        result = subprocess.run([sys.executable, str(script), "--help"],
                                cwd=script.parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--snapshot-only", result.stdout)

    def test_snapshot_saves_all_quotes_with_capture_time_and_replaces_same_hour(self):
        when = datetime(2026, 10, 10, 1, 25, tzinfo=timezone.utc)
        first = [
            {"instrument_name": "ETH-10OCT26-2500-C", "bid_price": 0.1,
             "ask_price": 0.2, "mark_price": 0.15, "mark_iv": 55.0},
            {"instrument_name": "ETH-10OCT26-2500-P", "bid_price": None,
             "ask_price": 0.3, "mark_price": 0.2, "mark_iv": 60.0},
        ]
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            meta = save_chain_snapshot(output, when, first)
            self.assertEqual(meta["row_count"], 2)
            path = output / "2026" / "10" / "10" / "01.jsonl.gz"
            with gzip.open(path, "rt") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["captured_at_ms"], 1791595500000)
            self.assertIsNone(rows[1]["bid_price"])
            self.assertEqual(rows[1]["mark_iv"], 60.0)
            save_chain_snapshot(output, when, first[:1])
            with gzip.open(path, "rt") as stream:
                self.assertEqual(len(stream.readlines()), 1)

    def test_empty_api_result_cannot_replace_existing_snapshot(self):
        when = datetime(2026, 10, 10, 1, 25, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            save_chain_snapshot(output, when, [{"instrument_name": "ETH-X", "mark_price": 1}])
            with self.assertRaisesRegex(RuntimeError, "empty"):
                save_chain_snapshot(output, when, [])
            path = output / "2026" / "10" / "10" / "01.jsonl.gz"
            with gzip.open(path, "rt") as stream:
                self.assertEqual(len(stream.readlines()), 1)


if __name__ == "__main__":
    unittest.main()
