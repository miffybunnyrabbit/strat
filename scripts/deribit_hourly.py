#!/usr/bin/env python3
"""Build honest hourly ETH option observations from trades and quote snapshots."""

import argparse
import csv
import gzip
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRADES = REPO_ROOT / "data/deribit/eth_option_trades"
DEFAULT_CHAIN = REPO_ROOT / "data/deribit/eth_option_chain"
DEFAULT_HOURLY = REPO_ROOT / "data/deribit/eth_option_hourly"
HOUR_MS = 3_600_000
FIELDS = [
    "hour_utc", "observed_at_utc", "instrument_name", "expiry_utc", "strike",
    "option_type", "dte_hours", "bid_price", "ask_price", "mark_price", "iv",
    "iv_kind", "trade_price", "trade_count", "source", "price_unit",
]


def contract_details(instrument_name, observed_at_ms, max_dte_days):
    parts = instrument_name.split("-")
    if len(parts) != 4 or parts[0] != "ETH" or parts[3] not in ("C", "P"):
        return None
    try:
        expiry = datetime.strptime(parts[1], "%d%b%y").replace(hour=8, tzinfo=timezone.utc)
        float(parts[2])
    except ValueError:
        return None
    dte_hours = (expiry.timestamp() * 1000 - observed_at_ms) / HOUR_MS
    if dte_hours < 0 or dte_hours > max_dte_days * 24:
        return None
    return expiry.isoformat(), parts[2], parts[3], round(dte_hours, 4)


def source_files(day, trade_dir, chain_dir):
    year, month, number = day.split("-")
    trade_path = Path(trade_dir) / year / month / f"{number}.jsonl.gz"
    quote_paths = sorted((Path(chain_dir) / year / month / number).glob("*.jsonl.gz"))
    return ([trade_path] if trade_path.exists() else []) + quote_paths


def convert_day(day, trade_dir, chain_dir, output_dir, max_dte_days=183):
    """Aggregate available observations for one UTC date, preserving source type."""
    inputs = source_files(day, trade_dir, chain_dir)
    if not inputs:
        raise FileNotFoundError(f"No trades or quotes for {day}")
    year, month, number = day.split("-")
    folder = Path(output_dir) / year / month
    folder.mkdir(parents=True, exist_ok=True)
    output_path = folder / f"{number}.csv.gz"
    meta_path = folder / f"{number}.meta.json"
    fingerprint = {str(path): [path.stat().st_size, path.stat().st_mtime_ns] for path in inputs}
    if output_path.exists() and meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text())
            if (existing["source_files"] == fingerprint and existing["max_dte_days"] == max_dte_days
                    and existing["compressed_bytes"] == output_path.stat().st_size):
                return existing
        except (OSError, ValueError, KeyError):
            pass

    rows = {}
    for path in inputs:
        is_quote = Path(chain_dir) in path.parents
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                stamp = record["captured_at_ms"] if is_quote else record["timestamp"]
                hour_ms = stamp // HOUR_MS * HOUR_MS
                name = record["instrument_name"]
                key = (hour_ms, name)
                previous = rows.get(key)
                if is_quote:
                    rows[key] = {
                        "observed_at_ms": stamp, "bid_price": record.get("bid_price"),
                        "ask_price": record.get("ask_price"), "mark_price": record.get("mark_price"),
                        "iv": record.get("mark_iv"), "iv_kind": "mark",
                        "trade_price": previous["trade_price"] if previous else None,
                        "trade_count": previous["trade_count"] if previous else 0,
                        "source": "chain_snapshot",
                    }
                elif previous is None:
                    rows[key] = {
                        "observed_at_ms": stamp, "bid_price": None, "ask_price": None,
                        "mark_price": record.get("mark_price"), "iv": record.get("iv"),
                        "iv_kind": "trade_price", "trade_price": record.get("price"),
                        "trade_count": 1, "source": "trade_mark_at_execution",
                    }
                else:
                    previous["trade_count"] += 1
                    if stamp >= previous["observed_at_ms"] and previous["source"] != "chain_snapshot":
                        previous.update({"observed_at_ms": stamp, "mark_price": record.get("mark_price"),
                                         "iv": record.get("iv"), "trade_price": record.get("price")})
                    elif previous["source"] == "chain_snapshot":
                        previous["trade_price"] = record.get("price")

    fd, temporary_name = tempfile.mkstemp(prefix=f".{number}.", suffix=".tmp", dir=folder)
    os.close(fd)
    temporary_path = Path(temporary_name)
    count = 0
    try:
        with gzip.open(temporary_path, "wt", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for (hour_ms, name), observation in sorted(rows.items()):
                details = contract_details(name, observation["observed_at_ms"], max_dte_days)
                if details is None:
                    continue
                expiry, strike, option_type, dte_hours = details
                row = {
                    "hour_utc": datetime.fromtimestamp(hour_ms / 1000, timezone.utc).isoformat(),
                    "observed_at_utc": datetime.fromtimestamp(observation["observed_at_ms"] / 1000, timezone.utc).isoformat(),
                    "instrument_name": name, "expiry_utc": expiry, "strike": strike,
                    "option_type": option_type, "dte_hours": dte_hours,
                    "price_unit": "ETH",
                }
                row.update({k: v for k, v in observation.items() if k != "observed_at_ms"})
                writer.writerow(row)
                count += 1
        meta = {
            "date_utc": day, "row_count": count, "max_dte_days": max_dte_days,
            "source_files": fingerprint, "compressed_bytes": temporary_path.stat().st_size,
        }
        os.replace(temporary_path, output_path)
        meta_tmp = meta_path.with_suffix(".json.tmp")
        meta_tmp.write_text(json.dumps(meta, indent=2) + "\n")
        os.replace(meta_tmp, meta_path)
        return meta
    finally:
        temporary_path.unlink(missing_ok=True)


def available_days(trade_dir, chain_dir):
    days = set()
    for path in Path(trade_dir).glob("*/*/*.jsonl.gz"):
        days.add(f"{path.parent.parent.name}-{path.parent.name}-{path.name[:2]}")
    for path in Path(chain_dir).glob("*/*/*/*.jsonl.gz"):
        days.add(f"{path.parent.parent.parent.name}-{path.parent.parent.name}-{path.parent.name}")
    return sorted(days)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="One UTC date; default is current UTC date")
    parser.add_argument("--all", action="store_true", help="Convert all available dates")
    parser.add_argument("--trade-dir", type=Path, default=DEFAULT_TRADES)
    parser.add_argument("--chain-dir", type=Path, default=DEFAULT_CHAIN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_HOURLY)
    parser.add_argument("--max-dte-days", type=int, default=183)
    args = parser.parse_args()
    if args.all and args.date:
        parser.error("choose --all or --date")
    if args.max_dte_days < 0:
        parser.error("--max-dte-days must be nonnegative")
    days = (available_days(args.trade_dir, args.chain_dir) if args.all
            else [args.date or datetime.now(timezone.utc).date().isoformat()])
    for day in days:
        meta = convert_day(day, args.trade_dir, args.chain_dir, args.output_dir, args.max_dte_days)
        print(f"{day} hourly_rows={meta['row_count']}", flush=True)


if __name__ == "__main__":
    main()
