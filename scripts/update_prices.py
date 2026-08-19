#!/usr/bin/env python3
"""Update latest completed daily closes for the NVIDIA 800 VDC dashboard.

The script intentionally stores end-of-day closes rather than intraday quotes. It keeps the
last successful value when a symbol fails, so one provider error does not blank the website.
"""
from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "data" / "market_prices.json"
JS_PATH = ROOT / "data" / "market_prices.js"
MAX_FAILED_SYMBOLS = 2

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
            payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return {"schemaVersion": 1, "prices": {}, "errors": []}


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def iso_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


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
            hist = ticker.history(period="1mo", interval="1d", auto_adjust=False, actions=False, repair=False)
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


def validate_snapshot(output_prices: dict, old_prices: dict, errors: list[dict]) -> None:
    expected = set(SYMBOLS)
    actual = set(output_prices)
    issues = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    error_tickers = {error.get("ticker") for error in errors}

    if missing:
        issues.append(f"missing tickers={missing}")
    if unexpected:
        issues.append(f"unexpected tickers={unexpected}")
    if len(errors) > MAX_FAILED_SYMBOLS:
        issues.append(f"errors={len(errors)} exceeds maximum={MAX_FAILED_SYMBOLS}")

    for key in sorted(expected & actual):
        meta = SYMBOLS[key]
        record = output_prices[key]
        if not isinstance(record, dict):
            issues.append(f"{key}: record is not an object")
            continue

        for field in ("symbol", "currency", "market"):
            if record.get(field) != meta[field]:
                issues.append(f"{key}: {field} mismatch")

        status = record.get("status")
        if status not in {"ok", "stale"}:
            issues.append(f"{key}: invalid status={status!r}")
        if not finite(record.get("close")) or float(record["close"]) <= 0:
            issues.append(f"{key}: invalid close")

        price_date = iso_date(record.get("priceDate"))
        if price_date is None:
            issues.append(f"{key}: invalid priceDate")
        else:
            market_today = datetime.now(ZoneInfo(meta["timezone"])).date()
            if price_date > market_today:
                issues.append(f"{key}: future priceDate={price_date}")

        history = record.get("history")
        if not isinstance(history, list):
            issues.append(f"{key}: history is not a list")
            history = []

        if status == "ok":
            if key in error_tickers:
                issues.append(f"{key}: marked ok but also has an error")
            if len(history) < 2:
                issues.append(f"{key}: successful history has fewer than 2 rows")
            else:
                history_dates = [iso_date(row.get("date")) for row in history if isinstance(row, dict)]
                history_closes = [row.get("close") for row in history if isinstance(row, dict)]
                if len(history_dates) != len(history) or any(value is None for value in history_dates):
                    issues.append(f"{key}: invalid history date")
                elif history_dates != sorted(history_dates):
                    issues.append(f"{key}: history dates are not sorted")
                if len(history_closes) != len(history) or any(not finite(value) or float(value) <= 0 for value in history_closes):
                    issues.append(f"{key}: invalid history close")
                if (
                    price_date is not None
                    and history_dates
                    and history_dates[-1] != price_date
                ):
                    issues.append(f"{key}: history does not end on priceDate")
                if (
                    history_closes
                    and finite(history_closes[-1])
                    and finite(record.get("close"))
                    and not math.isclose(float(history_closes[-1]), float(record["close"]), rel_tol=1e-9)
                ):
                    issues.append(f"{key}: history close does not match close")

            old_record = old_prices.get(key)
            old_date = iso_date(old_record.get("priceDate")) if isinstance(old_record, dict) else None
            if price_date is not None and old_date is not None and price_date < old_date:
                issues.append(f"{key}: priceDate regressed from {old_date} to {price_date}")
        elif key not in error_tickers:
            issues.append(f"{key}: stale without a current fetch error")

    if issues:
        raise RuntimeError("Market snapshot quality gate failed: " + "; ".join(issues))


def write_snapshot(payload: dict) -> None:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    js_text = "window.MARKET_PRICES = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    json_temp = JSON_PATH.with_name(f".{JSON_PATH.name}.tmp")
    js_temp = JS_PATH.with_name(f".{JS_PATH.name}.tmp")
    try:
        json_temp.write_text(json_text, encoding="utf-8")
        js_temp.write_text(js_text, encoding="utf-8")
        json_temp.replace(JSON_PATH)
        js_temp.replace(JS_PATH)
    finally:
        json_temp.unlink(missing_ok=True)
        js_temp.unlink(missing_ok=True)


def main() -> dict:
    existing = read_existing()
    old_prices = existing.get("prices", {})
    if not isinstance(old_prices, dict):
        old_prices = {}
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

    validate_snapshot(output_prices, old_prices, errors)
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance public market data via yfinance; latest completed daily close",
        "sourceType": "scheduled",
        "prices": output_prices,
        "errors": errors,
    }
    write_snapshot(payload)
    print(f"Wrote {len(output_prices)} prices; ok={len(SYMBOLS) - len(errors)}; errors={len(errors)}")
    return payload


if __name__ == "__main__":
    main()
