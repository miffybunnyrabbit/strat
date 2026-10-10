#!/usr/bin/env python3
"""Save a current ETH option-chain quote snapshot and refresh trade history."""

import argparse
import gzip
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

CHAIN_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHAIN_OUTPUT = REPO_ROOT / "data/deribit/eth_option_chain"
TRADE_OUTPUT = REPO_ROOT / "data/deribit/eth_option_trades"


def fetch_chain(retries=5):
    for attempt in range(retries + 1):
        try:
            response = requests.get(CHAIN_URL, params={"currency": "ETH", "kind": "option"}, timeout=(10, 60))
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(f"Deribit API error: {payload['error']}")
            rows = payload["result"]
            if not isinstance(rows, list) or not rows:
                raise RuntimeError("Deribit returned an empty or invalid ETH option chain")
            return rows
        except (requests.RequestException, ValueError, KeyError) as exc:
            if attempt == retries:
                raise RuntimeError(f"ETH option-chain request failed: {exc}") from exc
            time.sleep(min(30, 2 ** attempt + random.uniform(0, 0.5)))
    raise AssertionError("unreachable")


def save_chain_snapshot(output_dir, captured_at, rows):
    """Atomically save the latest snapshot in its UTC hour."""
    if not rows:
        raise RuntimeError("Cannot save an empty option-chain snapshot")
    output_dir = Path(output_dir)
    folder = output_dir / captured_at.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)
    hour = captured_at.strftime("%H")
    data_path = folder / f"{hour}.jsonl.gz"
    meta_path = folder / f"{hour}.meta.json"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{hour}.", suffix=".tmp", dir=folder)
    os.close(fd)
    temporary_path = Path(temporary_name)
    captured_at_ms = int(captured_at.timestamp() * 1000)
    try:
        with gzip.open(temporary_path, "wt", encoding="utf-8") as output:
            for source in rows:
                if not source["instrument_name"].startswith("ETH-"):
                    raise RuntimeError(f"Unexpected instrument: {source['instrument_name']}")
                row = dict(source)
                row["captured_at_ms"] = captured_at_ms
                output.write(json.dumps(row, separators=(",", ":")) + "\n")
        meta = {
            "captured_at_utc": captured_at.isoformat(), "captured_at_ms": captured_at_ms,
            "row_count": len(rows), "compressed_bytes": temporary_path.stat().st_size,
            "source": CHAIN_URL, "kind": "option", "currency": "ETH",
        }
        os.replace(temporary_path, data_path)
        meta_tmp = meta_path.with_suffix(".json.tmp")
        meta_tmp.write_text(json.dumps(meta, indent=2) + "\n")
        os.replace(meta_tmp, meta_path)
        return meta
    finally:
        temporary_path.unlink(missing_ok=True)


def backfill_is_running(trade_output):
    pid_path = trade_output / "backfill.pid"
    try:
        pid = int(pid_path.read_text().strip())
        command = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                 capture_output=True, text=True, check=False)
        return command.returncode == 0 and "deribit_backfill.py" in command.stdout
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--backfill-only", action="store_true")
    parser.add_argument("--chain-output-dir", type=Path, default=DEFAULT_CHAIN_OUTPUT)
    parser.add_argument("--trade-output-dir", type=Path, default=TRADE_OUTPUT)
    args = parser.parse_args()
    if args.snapshot_only and args.backfill_only:
        parser.error("choose one of --snapshot-only and --backfill-only")

    if not args.backfill_only:
        rows = fetch_chain()
        meta = save_chain_snapshot(args.chain_output_dir, datetime.now(timezone.utc), rows)
        print(f"Saved option chain: {meta['row_count']} contracts at {meta['captured_at_utc']}", flush=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("deribit_hourly.py")),
                        "--date", meta["captured_at_utc"][:10],
                        "--trade-dir", str(args.trade_output_dir.resolve()),
                        "--chain-dir", str(args.chain_output_dir.resolve())], check=True)

    if not args.snapshot_only:
        if backfill_is_running(args.trade_output_dir):
            print("Trade backfill is already running; trade refresh skipped.", flush=True)
            return
        script = Path(__file__).with_name("deribit_backfill.py")
        subprocess.run([sys.executable, "-u", str(script), "--output-dir",
                        str(args.trade_output_dir.resolve())], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name("deribit_hourly.py")),
                        "--all", "--trade-dir", str(args.trade_output_dir.resolve()),
                        "--chain-dir", str(args.chain_output_dir.resolve())], check=True)


if __name__ == "__main__":
    main()
