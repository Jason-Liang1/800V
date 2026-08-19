from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from scripts import update_prices as updater


def ok_record(key: str, price_date: str = "2025-01-03") -> dict:
    meta = updater.SYMBOLS[key]
    return {
        "symbol": meta["symbol"],
        "close": 101.0,
        "previousClose": 100.0,
        "change": 1.0,
        "changePct": 1.0,
        "currency": meta["currency"],
        "priceDate": price_date,
        "market": meta["market"],
        "history": [
            {"date": "2025-01-02", "close": 100.0},
            {"date": price_date, "close": 101.0},
        ],
        "status": "ok",
    }


def snapshot_with_failures(failure_count: int) -> tuple[dict, dict, list[dict]]:
    old_prices = {key: ok_record(key) for key in updater.SYMBOLS}
    prices = {key: ok_record(key) for key in updater.SYMBOLS}
    errors = []
    for key in list(updater.SYMBOLS)[:failure_count]:
        prices[key]["status"] = "stale"
        prices[key]["error"] = "provider unavailable"
        errors.append(
            {
                "ticker": key,
                "symbol": updater.SYMBOLS[key]["symbol"],
                "error": "provider unavailable",
            }
        )
    return prices, old_prices, errors


class PriceUpdaterTests(unittest.TestCase):
    def test_fetch_disables_optional_price_repair(self) -> None:
        meta = updater.SYMBOLS["2308"]
        history = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"], tz=meta["timezone"]),
        )
        ticker = MagicMock()
        ticker.history.return_value = history

        with patch.object(updater.yf, "Ticker", return_value=ticker):
            result = updater.fetch_one("2308", meta)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["history"]), 2)
        self.assertFalse(ticker.history.call_args.kwargs["repair"])

    def test_quality_gate_accepts_two_stale_symbols(self) -> None:
        prices, old_prices, errors = snapshot_with_failures(2)
        updater.validate_snapshot(prices, old_prices, errors)

    def test_quality_gate_rejects_three_failed_symbols(self) -> None:
        prices, old_prices, errors = snapshot_with_failures(3)
        with self.assertRaisesRegex(RuntimeError, "errors=3 exceeds maximum=2"):
            updater.validate_snapshot(prices, old_prices, errors)

    def test_quality_gate_rejects_missing_symbol(self) -> None:
        prices, old_prices, errors = snapshot_with_failures(0)
        prices.pop("2308")
        with self.assertRaisesRegex(RuntimeError, "missing tickers"):
            updater.validate_snapshot(prices, old_prices, errors)

    def test_quality_gate_rejects_invalid_history_and_date_regression(self) -> None:
        prices, old_prices, errors = snapshot_with_failures(0)
        prices["2308"]["history"] = []
        old_prices["2301"]["priceDate"] = "2025-01-04"
        with self.assertRaisesRegex(RuntimeError, "history has fewer than 2 rows"):
            updater.validate_snapshot(prices, old_prices, errors)
        with self.assertRaisesRegex(RuntimeError, "priceDate regressed"):
            updater.validate_snapshot(prices, old_prices, errors)

    def test_failed_gate_preserves_existing_files(self) -> None:
        prices, _, _ = snapshot_with_failures(0)
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "market_prices.json"
            js_path = Path(temp_dir) / "market_prices.js"
            json_path.write_text("existing-json", encoding="utf-8")
            js_path.write_text("existing-js", encoding="utf-8")

            with (
                patch.object(updater, "JSON_PATH", json_path),
                patch.object(updater, "JS_PATH", js_path),
                patch.object(updater, "read_existing", return_value={"prices": prices}),
                patch.object(updater, "fetch_one", side_effect=RuntimeError("provider unavailable")),
            ):
                with self.assertRaisesRegex(RuntimeError, "quality gate failed"):
                    updater.main()

            self.assertEqual(json_path.read_text(encoding="utf-8"), "existing-json")
            self.assertEqual(js_path.read_text(encoding="utf-8"), "existing-js")

    def test_successful_main_writes_matching_json_and_js(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "market_prices.json"
            js_path = Path(temp_dir) / "market_prices.js"

            with (
                patch.object(updater, "JSON_PATH", json_path),
                patch.object(updater, "JS_PATH", js_path),
                patch.object(updater, "read_existing", return_value={"prices": {}}),
                patch.object(updater, "fetch_one", side_effect=lambda key, meta: ok_record(key)),
            ):
                payload = updater.main()

            stored = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(stored, payload)
            self.assertEqual(stored["errors"], [])
            self.assertTrue(all(record["status"] == "ok" for record in stored["prices"].values()))
            self.assertEqual(
                js_path.read_text(encoding="utf-8"),
                "window.MARKET_PRICES = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
            )


if __name__ == "__main__":
    unittest.main()
