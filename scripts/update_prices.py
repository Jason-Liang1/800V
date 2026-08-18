#!/usr/bin/env python3
"""Update latest completed daily closes for the NVIDIA 800 VDC dashboard.

The script intentionally stores end-of-day closes rather than intraday quotes. It keeps the
last successful value when a symbol fails, so one provider error does not blank the website.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "data" / "market_prices.json"
JS_PATH = ROOT / "data" / "market_prices.js"

SYMBOLS = {
    "2308": {"symbol": "2308.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "2301": {"symbol": "2301.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "3665": {"symbol": "3665.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "2454": {"symbol": "2454.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "3017": {"symbol": "3017.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "3324": {"symbol": "3324.TWO", "currency": "TWD", "market": "TPEX", "timezone": "Asia/Taipei", "close": "13:30"},
    "1519": {"symbol": "1519.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "1513": {"symbol": "1513.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "1503": {"symbol": "1503.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "6412": {"symbol": "6412.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "6282": {"symbol": "6282.TW", "currency": "TWD", "market": "TWSE", "timezone": "Asia/Taipei", "close": "13:30"},
    "VRT": {"symbol": "VRT", "currency": "USD", "market": "NYSE", "timezone": "America/New_York", "close": "16:00"},
    "ETN": {"symbol": "ETN", "currency": "USD", "market": "NYSE", "timezone": "America/New_York", "close": "16:00"},
    "FLEX": {"symbol": "FLEX", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "TXN": {"symbol": "TXN", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "ON": {"symbol": "ON", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "ABB": {"symbol": "ABBNY", "currency": "USD", "market": "OTC", "timezone": "America/New_York", "close": "16:00"},
    "GEV": {"symbol": "GEV", "currency": "USD", "market": "NYSE", "timezone": "America/New_York", "close": "16:00"},
    "AOSL": {"symbol": "AOSL", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "POWI": {"symbol": "POWI", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "NVTS": {"symbol": "NVTS", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "MPWR": {"symbol": "MPWR", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
    "ADI": {"symbol": "ADI", "currency": "USD", "market": "NASDAQ", "timezone": "America/New_York", "close": "16:00"},
}


def read_existing() -> dict:
    if JSON_PATH.exists():
        try:
            return json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"schemaVersion": 1, "prices": {}, "errors": []}


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def completed_rows(hist: pd.DataFrame, meta: dict) -> pd.DataFrame:
    hist = hist.copy()
    hist = hist[hist["Close"].notna()]
    if hist.empty:
        return hist

    tz = ZoneInfo(meta["timezone"])
    now = datetime.now(tz)
    hh, mm = [int(x) for x in meta["close"].split(":")]
    cutoff = datetime.combine(now.date(), dt_time(hh, mm), tzinfo=tz) + timedelta(minutes=20)

    last_index = hist.index[-1]
    if isinstance(last_index, pd.Timestamp):
        if last_index.tzinfo is None:
            last_local = last_index.tz_localize(tz)
        else:
            last_local = last_index.tz_convert(tz)
    else:
        last_local = pd.Timestamp(last_index).tz_localize(tz)

    # Daily bars can appear before the official close. Drop today's row until the close plus buffer.
    if last_local.date() == now.date() and now < cutoff:
        hist = hist.iloc[:-1]
    return hist


def fetch_one(key: str, meta: dict) -> dict:
    last_error = None
    for attempt in range(3):
        try:
            ticker = yf.Ticker(meta["symbol"])
            hist = ticker.history(period="1mo", interval="1d", auto_adjust=False, actions=False, repair=True)
            hist = completed_rows(hist, meta)
            if len(hist) < 1:
                raise RuntimeError("no completed daily close")

            closes = hist["Close"].dropna()
            close = float(closes.iloc[-1])
            previous = float(closes.iloc[-2]) if len(closes) >= 2 else None
            if not finite(close):
                raise RuntimeError("invalid close")

            idx = closes.index[-1]
            tz = ZoneInfo(meta["timezone"])
            if isinstance(idx, pd.Timestamp):
                idx_local = idx.tz_localize(tz) if idx.tzinfo is None else idx.tz_convert(tz)
                price_date = idx_local.date().isoformat()
            else:
                price_date = str(idx)[:10]

            history = []
            for date_idx, value in closes.tail(20).items():
                if not finite(value):
                    continue
                if isinstance(date_idx, pd.Timestamp):
                    date_local = date_idx.tz_localize(tz) if date_idx.tzinfo is None else date_idx.tz_convert(tz)
                    date_str = date_local.date().isoformat()
                else:
                    date_str = str(date_idx)[:10]
                history.append({"date": date_str, "close": round(float(value), 6)})

            change = close - previous if previous is not None else None
            return {
                "symbol": meta["symbol"],
                "close": round(close, 6),
                "previousClose": round(previous, 6) if previous is not None else None,
                "change": round(change, 6) if change is not None else None,
                "changePct": round((close / previous - 1) * 100, 6) if previous else None,
                "currency": meta["currency"],
                "priceDate": price_date,
                "market": meta["market"],
                "history": history,
                "status": "ok",
            }
        except Exception as exc:  # provider failures are retried, then preserved as stale data
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2 + attempt * 3)
    raise RuntimeError(last_error or "unknown price error")


def main() -> None:
    existing = read_existing()
    old_prices = existing.get("prices", {})
    output_prices = {}
    errors = []

    for key, meta in SYMBOLS.items():
        try:
            output_prices[key] = fetch_one(key, meta)
            print(f"OK {key:>5} {output_prices[key]['priceDate']} {output_prices[key]['close']}")
        except Exception as exc:
            old = old_prices.get(key)
            if old:
                output_prices[key] = dict(old)
                output_prices[key]["status"] = "stale"
                output_prices[key]["error"] = str(exc)
            errors.append({"ticker": key, "symbol": meta["symbol"], "error": str(exc)})
            print(f"ERR {key:>5} {exc}")

    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance public market data via yfinance; latest completed daily close",
        "sourceType": "scheduled",
        "prices": output_prices,
        "errors": errors,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    JS_PATH.write_text("window.MARKET_PRICES = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    print(f"Wrote {len(output_prices)} prices; errors={len(errors)}")


if __name__ == "__main__":
    main()
