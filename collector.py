"""Public price receipts only. No strategies, accounts, credentials or orders."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
import uuid

ORIGIN = "https://data-api.binance.vision"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVALS = {"1d": 86_400_000, "4h": 14_400_000}
MAX_BYTES = 65_536
MAX_REQUESTS = 5


def now_ms():
    return time.time_ns() // 1_000_000


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("REDIRECT_FORBIDDEN")


class PublicClient:
    def __init__(self, clock=now_ms):
        self.clock = clock
        self.requests = 0
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())

    def get(self, endpoint, parameters):
        if endpoint == "/api/v3/time":
            valid = parameters == {}
        elif endpoint == "/api/v3/klines":
            valid = (set(parameters) == {"symbol", "interval", "startTime", "endTime", "limit"}
                     and parameters["symbol"] in SYMBOLS and parameters["interval"] in INTERVALS
                     and parameters["limit"] == 1
                     and type(parameters["startTime"]) is int and type(parameters["endTime"]) is int)
        else:
            valid = False
        if not valid:
            raise RuntimeError("PUBLIC_REQUEST_NOT_ALLOWED")
        if self.requests >= MAX_REQUESTS:
            raise RuntimeError("REQUEST_BUDGET_EXHAUSTED")
        self.requests += 1
        sent = self.clock()
        url = ORIGIN + endpoint + ("?" + urlencode(parameters) if parameters else "")
        request = Request(url, headers={"User-Agent": "Tiempoficio-Public-Observer/1.0", "Accept": "application/json"}, method="GET")
        with self.opener.open(request, timeout=15) as response:
            if response.status != 200 or response.geturl() != url:
                raise RuntimeError("UNEXPECTED_PUBLIC_RESPONSE")
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise RuntimeError("RESPONSE_TOO_LARGE")
        received = self.clock()
        if received < sent:
            raise RuntimeError("LOCAL_CLOCK_REVERSED")
        return json.loads(body), {"endpoint": endpoint, "parameters": parameters,
                                  "sent_at_ms": sent, "received_at_ms": received,
                                  "response_sha256": hashlib.sha256(body).hexdigest()}


def candle(raw, start, interval):
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], list) or len(raw[0]) != 12:
        raise RuntimeError("CANDLE_SHAPE_INVALID")
    row = raw[0]
    if type(row[0]) is not int or type(row[6]) is not int or row[0] != start or row[6] != start + interval - 1:
        raise RuntimeError("CANDLE_BOUNDARY_INVALID")
    try:
        values = [Decimal(str(row[i])) for i in range(1, 6)]
    except (InvalidOperation, ValueError):
        raise RuntimeError("CANDLE_NUMBERS_INVALID") from None
    if not all(v.is_finite() for v in values):
        raise RuntimeError("CANDLE_NUMBERS_INVALID")
    opening, high, low, close, volume = values
    if min(opening, high, low, close) <= 0 or volume < 0 or low > min(opening, close) or high < max(opening, close) or high < low:
        raise RuntimeError("CANDLE_OHLCV_INVALID")
    return {"open_ms": row[0], "close_ms": row[6],
            **dict(zip(("open", "high", "low", "close", "volume"), map(str, values)))}


def capture(client, *, clock=now_ms):
    server, receipt = client.get("/api/v3/time", {})
    if (not isinstance(server, dict) or type(server.get("serverTime")) is not int
            or abs(server["serverTime"] - receipt["received_at_ms"]) > 120_000
            or receipt["received_at_ms"] < receipt["sent_at_ms"]
            or abs(clock() - receipt["received_at_ms"]) > 120_000):
        raise RuntimeError("SERVER_CLOCK_INVALID")
    cutoff = min(server["serverTime"], receipt["received_at_ms"])
    receipts = [{**receipt, "server_time_ms": server["serverTime"]}]
    for symbol in SYMBOLS:
        for tf, interval in INTERVALS.items():
            end = cutoff // interval * interval
            start = end - interval
            params = {"symbol": symbol, "interval": tf, "startTime": start, "endTime": end - 1, "limit": 1}
            raw, received = client.get("/api/v3/klines", params)
            if (received["received_at_ms"] < received["sent_at_ms"] or received["received_at_ms"] < cutoff
                    or abs(received["received_at_ms"] - clock()) > 120_000):
                raise RuntimeError("RECEIPT_CLOCK_INVALID")
            value = candle(raw, start, interval)
            receipts.append({**received, "symbol": symbol, "timeframe": tf, "candle": value,
                             "lateness_ms": received["received_at_ms"] - end})
    finished = clock()
    return {"schema": "public-price-receipt-v1", "started_at_ms": receipt["sent_at_ms"],
            "completed_at_ms": finished, "source": ORIGIN, "receipts": receipts,
            "safety": {"public_prices_only": True, "strategy_evaluated": False,
                       "paper_allowed": False, "live_allowed": False, "orders_allowed": False,
                       "exchange_credentials_used": False, "real_capital_eur": 0},
            "limitations": ["Price receipts, not strategy signals or evidence of profitability.",
                            "Later recovery cannot recreate an earlier receipt or decision."]}


def provenance(environment):
    if environment.get("GITHUB_ACTIONS") != "true":
        return {"runtime": "local", "capture_id": "local-" + uuid.uuid4().hex}
    if environment.get("OBSERVER_REPOSITORY_PUBLIC") != "true":
        raise RuntimeError("PUBLIC_REPOSITORY_REQUIRED")
    run = environment.get("GITHUB_RUN_ID", "")
    attempt = environment.get("GITHUB_RUN_ATTEMPT", "")
    commit = environment.get("GITHUB_SHA", "")
    repository = environment.get("GITHUB_REPOSITORY", "")
    if (not run.isascii() or not run.isdigit() or not attempt.isascii() or not attempt.isdigit()
            or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)):
        raise RuntimeError("RUN_PROVENANCE_INVALID")
    return {"runtime": "github-actions", "capture_id": run + "-" + attempt,
            "repository": repository, "source_commit": commit, "run_id": run, "attempt": attempt}


def save(output: Path, value, origin):
    complete = {**value, "provenance": origin}
    complete["content_sha256"] = hashlib.sha256(encode(complete)).hexdigest()
    day = datetime.fromtimestamp(value["completed_at_ms"] / 1000, timezone.utc).strftime("%Y-%m-%d")
    directory = output / day
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (origin["capture_id"] + ".json")
    with target.open("xb") as handle:
        handle.write(encode(complete) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data"))
    args = parser.parse_args()
    try:
        origin = provenance(os.environ)
        result = capture(PublicClient())
        target = save(args.output, result, origin)
    except (RuntimeError, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("CAPTURE_FAILED: " + code)
        return 1
    print("Public price receipt saved: " + str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
