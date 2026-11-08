import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from collector import PublicClient, capture, candle, encode, provenance, save

NOW = 1_800_000_060_000


def row(start, interval):
    return [start, "10", "12", "9", "11", "50", start + interval - 1, "0", 5, "0", "0", "0"]


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, parameters):
        self.calls.append((endpoint, parameters))
        if endpoint.endswith("time"):
            body = {"serverTime": NOW}
        else:
            interval = 86_400_000 if parameters["interval"] == "1d" else 14_400_000
            body = [row(parameters["startTime"], interval)]
        return body, {"endpoint": endpoint, "parameters": parameters, "sent_at_ms": NOW,
                      "received_at_ms": NOW, "response_sha256": hashlib.sha256(encode(body)).hexdigest()}


class CollectorTests(unittest.TestCase):
    def test_closed_candles_only_and_five_public_requests(self):
        client = FakeClient()
        value = capture(client, clock=lambda: NOW)
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(len(value["receipts"]), 5)
        for receipt in value["receipts"][1:]:
            self.assertLess(receipt["candle"]["close_ms"], NOW)
            self.assertGreaterEqual(receipt["lateness_ms"], 0)
        self.assertFalse(value["safety"]["strategy_evaluated"])
        self.assertFalse(value["safety"]["orders_allowed"])

    def test_no_arbitrary_endpoint_or_credentials(self):
        client = PublicClient()
        for endpoint, params in (("/api/v3/order", {}), ("https://other.invalid", {}),
                                 ("/api/v3/time", {"apiKey": "not-a-key"})):
            with self.assertRaisesRegex(RuntimeError, "PUBLIC_REQUEST_NOT_ALLOWED"):
                client.get(endpoint, params)
        self.assertEqual(client.requests, 0)

    def test_request_budget(self):
        client = PublicClient()
        client.requests = 5
        with self.assertRaisesRegex(RuntimeError, "REQUEST_BUDGET_EXHAUSTED"):
            client.get("/api/v3/time", {})

    def test_invalid_server_clock(self):
        client = FakeClient()
        with self.assertRaisesRegex(RuntimeError, "SERVER_CLOCK_INVALID"):
            capture(client, clock=lambda: NOW + 130_000)

    def test_bad_ohlcv_and_nonfinite_values(self):
        for index, wrong in ((1, "NaN"), (2, "1"), (3, "13"), (4, "-1"), (5, "-1")):
            broken = row(0, 1000)
            broken[index] = wrong
            with self.assertRaises(RuntimeError):
                candle([broken], 0, 1000)

    def test_wrong_close_and_shape(self):
        with self.assertRaisesRegex(RuntimeError, "CANDLE_BOUNDARY_INVALID"):
            candle([row(0, 1000)], 0, 2000)
        with self.assertRaisesRegex(RuntimeError, "CANDLE_SHAPE_INVALID"):
            candle([], 0, 1000)

    def test_save_is_immutable_and_hash_is_reproducible(self):
        value = capture(FakeClient(), clock=lambda: NOW)
        with tempfile.TemporaryDirectory() as temporary:
            target = save(Path(temporary), value, {"capture_id": "1-1", "runtime": "test"})
            saved = json.loads(target.read_text(encoding="utf-8"))
            checksum = saved.pop("content_sha256")
            self.assertEqual(checksum, hashlib.sha256(encode(saved)).hexdigest())
            with self.assertRaises(FileExistsError):
                save(Path(temporary), value, {"capture_id": "1-1", "runtime": "test"})

    def test_private_repository_refused(self):
        with self.assertRaisesRegex(RuntimeError, "PUBLIC_REPOSITORY_REQUIRED"):
            provenance({"GITHUB_ACTIONS": "true"})

    def test_actions_provenance_and_allowlisted_environment(self):
        environment = {"GITHUB_ACTIONS": "true", "OBSERVER_REPOSITORY_PUBLIC": "true",
                       "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40,
                       "GITHUB_REPOSITORY": "Tiempoficio/markets-public-observer", "UNRELATED_SECRET": "must-not-appear"}
        result = provenance(environment)
        self.assertEqual(result["capture_id"], "123-1")
        self.assertNotIn("must-not-appear", json.dumps(result))
        environment["GITHUB_RUN_ID"] = "../private"
        with self.assertRaisesRegex(RuntimeError, "RUN_PROVENANCE_INVALID"):
            provenance(environment)

    def test_local_capture_never_claims_github(self):
        self.assertEqual(provenance({})["runtime"], "local")


if __name__ == "__main__":
    unittest.main()
