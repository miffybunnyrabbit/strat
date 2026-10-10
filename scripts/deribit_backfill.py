#!/usr/bin/env python3
"""Resumable, lossless daily backfill of Deribit ETH option trade records."""

import argparse
import gzip
import json
import os
import random
import signal
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


API_URL = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
DAY_MS = 86_400_000
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data/deribit/eth_option_trades"


def collect_interval(fetch, start_ms, end_ms):
    """Yield every trade in an inclusive window, splitting truncated responses."""
    trades, has_more = fetch(start_ms, end_ms)
    if not has_more:
        yield from trades
        return
    if not trades:
        raise RuntimeError("Deribit reported more trades but returned an empty page")
    if start_ms == end_ms:
        raise RuntimeError("More than 1000 trades in a single millisecond; cannot safely paginate")
    middle = (start_ms + end_ms) // 2
    yield from collect_interval(fetch, start_ms, middle)
    yield from collect_interval(fetch, middle + 1, end_ms)


class DeribitClient:
    def __init__(self, delay=0.25, retries=8):
        self.session = requests.Session()
        self.delay = delay
        self.retries = retries
        self.last_request = 0.0
        self.request_count = 0

    def fetch(self, start_ms, end_ms):
        params = {
            "currency": "ETH", "kind": "option", "start_timestamp": start_ms,
            "end_timestamp": end_ms, "count": 1000, "sorting": "asc",
        }
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            self.last_request = time.monotonic()
            self.request_count += 1
            try:
                response = self.session.get(API_URL, params=params, timeout=(10, 60))
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}")
                response.raise_for_status()
                payload = response.json()
                if "error" in payload:
                    error = payload["error"]
                    message = str(error)
                    if not any(word in message.lower() for word in ("rate", "too_many", "overload", "unavailable")):
                        raise RuntimeError(f"Deribit API error: {message}")
                    raise requests.HTTPError(message)
                result = payload["result"]
                trades = result["trades"]
                has_more = result["has_more"]
                if not isinstance(trades, list) or not isinstance(has_more, bool):
                    raise RuntimeError("Unexpected Deribit response shape")
                for trade in trades:
                    stamp = trade["timestamp"]
                    if not start_ms <= stamp <= end_ms:
                        raise RuntimeError(f"Trade outside requested interval: {stamp}")
                    if not trade["instrument_name"].startswith("ETH-"):
                        raise RuntimeError(f"Unexpected instrument: {trade['instrument_name']}")
                return trades, has_more
            except (requests.RequestException, ValueError, KeyError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Deribit request failed after retries: {exc}") from exc
                time.sleep(min(60.0, 2 ** attempt + random.uniform(0, 0.5)))
        raise AssertionError("unreachable")


def output_paths(output_dir, day):
    year, month, number = day.split("-")
    folder = output_dir / year / month
    return folder / f"{number}.jsonl.gz", folder / f"{number}.meta.json"


def download_day(output_dir, day, start_ms, end_ms, fetch):
    """Write a day atomically; reuse it only if its requested range matches."""
    output_dir = Path(output_dir)
    data_path, meta_path = output_paths(output_dir, day)
    if data_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if (meta["start_ms"] == start_ms and meta["end_ms"] == end_ms
                    and meta["compressed_bytes"] == data_path.stat().st_size):
                return meta
        except (OSError, ValueError, KeyError):
            pass

    data_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{day}.", suffix=".tmp", dir=data_path.parent)
    os.close(fd)
    temporary_path = Path(temporary_name)
    count = 0
    first = None
    last = None
    seen = set()
    try:
        with gzip.open(temporary_path, "wt", encoding="utf-8") as output:
            for trade in collect_interval(fetch, start_ms, end_ms):
                trade_id = trade["trade_id"]
                if trade_id in seen:
                    raise RuntimeError(f"Duplicate Deribit trade ID in {day}: {trade_id}")
                seen.add(trade_id)
                stamp = trade["timestamp"]
                if not start_ms <= stamp <= end_ms:
                    raise RuntimeError(f"Trade outside day: {stamp}")
                output.write(json.dumps(trade, separators=(",", ":")) + "\n")
                first = stamp if first is None else min(first, stamp)
                last = stamp if last is None else max(last, stamp)
                count += 1
        compressed_bytes = temporary_path.stat().st_size
        meta = {
            "date_utc": day, "start_ms": start_ms, "end_ms": end_ms,
            "trade_count": count, "first_trade_ms": first, "last_trade_ms": last,
            "compressed_bytes": compressed_bytes, "source": API_URL,
            "kind": "option", "currency": "ETH",
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        os.replace(temporary_path, data_path)
        meta_tmp = meta_path.with_suffix(".json.tmp")
        meta_tmp.write_text(json.dumps(meta, indent=2) + "\n")
        os.replace(meta_tmp, meta_path)
        return meta
    finally:
        temporary_path.unlink(missing_ok=True)


def status(output_dir):
    total_days = total_trades = total_bytes = 0
    latest = None
    for path in sorted(Path(output_dir).glob("*/*/*.meta.json")):
        try:
            meta = json.loads(path.read_text())
            data_path = path.with_name(path.name.replace(".meta.json", ".jsonl.gz"))
            if not data_path.exists() or data_path.stat().st_size != meta["compressed_bytes"]:
                continue
            total_days += 1
            total_trades += meta["trade_count"]
            total_bytes += meta["compressed_bytes"]
            latest = max(latest or meta["date_utc"], meta["date_utc"])
        except (OSError, ValueError, KeyError):
            continue
    print(json.dumps({"days": total_days, "trades": total_trades,
                      "compressed_bytes": total_bytes, "latest_date_utc": latest}, indent=2))


def main():
    now = datetime.now(timezone.utc)
    try:
        three_years_ago = now.date().replace(year=now.year - 3)
    except ValueError:  # 29 February
        three_years_ago = now.date().replace(year=now.year - 3, day=28)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default=three_years_ago.isoformat(), help="UTC start date, inclusive")
    parser.add_argument("--end-date", help="UTC end date, exclusive; default is current UTC time")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-days", type=int, help="Process only this many dates, for a trial run")
    parser.add_argument("--delay", type=float, default=0.25, help="Minimum seconds between API requests")
    parser.add_argument("--status", action="store_true", help="Report saved days and exit")
    args = parser.parse_args()
    if args.status:
        status(args.output_dir)
        return
    start_day = date.fromisoformat(args.start_date)
    end_ms = (int(datetime.combine(date.fromisoformat(args.end_date), datetime.min.time(), timezone.utc).timestamp() * 1000) - 1
              if args.end_date else int(now.timestamp() * 1000))
    if args.delay < 0 or (args.max_days is not None and args.max_days < 1):
        parser.error("--delay must be nonnegative and --max-days must be positive")
    if int(datetime.combine(start_day, datetime.min.time(), timezone.utc).timestamp() * 1000) > end_ms:
        parser.error("start date must be before end time")

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    client = DeribitClient(delay=args.delay)
    day = start_day
    processed = 0
    while int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() * 1000) <= end_ms:
        day_start = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() * 1000)
        day_end = min(day_start + DAY_MS - 1, end_ms)
        before = client.request_count
        meta = download_day(args.output_dir, day.isoformat(), day_start, day_end, client.fetch)
        print(f"{day.isoformat()} trades={meta['trade_count']} requests={client.request_count - before} ",
              f"bytes={meta['compressed_bytes']}", flush=True)
        day += timedelta(days=1)
        processed += 1
        if args.max_days and processed >= args.max_days:
            break
    print("Backfill run reached its end time.", flush=True)


if __name__ == "__main__":
    main()
