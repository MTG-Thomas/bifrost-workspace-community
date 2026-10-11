"""Generated SDK retries must not repeat non-idempotent operations."""

import unittest

from modules import halopsa, immybot


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}


class _SequenceSession:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


class GeneratedSDKRetryPolicyTests(unittest.TestCase):
    CLIENTS = (halopsa._HaloAPIClient, immybot._ImmyBotAPIClient)

    def test_post_is_not_retried_after_transient_response(self):
        for client_type in self.CLIENTS:
            with self.subTest(client=client_type.__name__):
                session = _SequenceSession(_Response(429), _Response(200))
                client = client_type(
                    "https://api.example.test",
                    session,
                    base_backoff=0,
                )

                response = client._request_with_retry(
                    "POST",
                    "https://api.example.test/items",
                    json={"name": "new"},
                )

                self.assertEqual(response.status_code, 429)
                self.assertEqual(len(session.calls), 1)

    def test_idempotent_request_is_retried_after_transient_response(self):
        for client_type in self.CLIENTS:
            with self.subTest(client=client_type.__name__):
                session = _SequenceSession(_Response(503), _Response(200))
                client = client_type(
                    "https://api.example.test",
                    session,
                    base_backoff=0,
                )

                response = client._request_with_retry(
                    "GET",
                    "https://api.example.test/items",
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(session.calls), 2)


if __name__ == "__main__":
    unittest.main()
