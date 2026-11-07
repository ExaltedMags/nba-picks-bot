"""Regressions for Gemini endpoint selection and bounded API retries."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx2
from google import genai
from google.genai import errors, types

import summarize


PICKS = {"picks": [{"game": "Boston vs. New York", "pick": "Boston ML"}]}
GOOD_RESPONSE = SimpleNamespace(text=json.dumps(PICKS))


def api_error(code, message, details=None):
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, payload)


class GeminiTests(unittest.TestCase):
    def summarize(self):
        return summarize.summarize_with_gemini(
            "I like Boston moneyline.", None, "Test Channel", "NBA Picks"
        )

    def test_real_sdk_sends_beta_endpoint_with_system_instruction_and_json(self):
        """Exercise SDK serialization: an SDK upgrade changed its default to v1."""
        requests = []

        def handler(request):
            requests.append(request)
            return httpx2.Response(
                200,
                json={
                    "candidates": [{
                        "content": {"parts": [{"text": json.dumps(PICKS)}]},
                        "finishReason": "STOP",
                    }]
                },
            )

        real_client = genai.Client
        with httpx2.Client(
            transport=httpx2.MockTransport(handler), trust_env=False
        ) as transport:
            def make_client(**kwargs):
                options = kwargs.pop("http_options", types.HttpOptions())
                options = options.model_copy(update={"httpx_client": transport})
                return real_client(**kwargs, http_options=options, vertexai=False)

            with patch.object(summarize, "GEMINI_API_KEY", "test-key"), patch.object(
                summarize.genai, "Client", side_effect=make_client
            ) as factory:
                result = self.summarize()

        self.assertEqual(result["picks"][0]["pick"], "Boston ML")
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url.path,
            f"/v1beta/models/{summarize.GEMINI_MODEL}:generateContent",
        )
        body = json.loads(requests[0].content)
        self.assertEqual(
            body["systemInstruction"]["parts"][0]["text"], summarize.SYSTEM_PROMPT
        )
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(factory.call_args.kwargs["http_options"].retry_options.attempts, 1)

    def test_permanent_client_errors_stop_after_one_attempt(self):
        for code in (400, 401, 403, 404):
            with self.subTest(code=code):
                client = Mock()
                message = "Developer instruction requires v1beta" if code == 400 else "Check API configuration"
                client.models.generate_content.side_effect = api_error(code, message)
                with patch.object(summarize.genai, "Client", return_value=client), patch.object(
                    summarize.time, "sleep"
                ) as sleep:
                    result = self.summarize()
                self.assertFalse(result["retryable"])
                self.assertIn(message, result["degraded"])
                client.models.generate_content.assert_called_once()
                sleep.assert_not_called()

    def test_daily_quota_does_not_retry(self):
        for violation in (
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"},
            {"description": "Generate content requests per day limit exceeded"},
        ):
            with self.subTest(violation=violation):
                client = Mock()
                client.models.generate_content.side_effect = api_error(
                    429, "Daily request quota exhausted", [
                        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [violation]},
                        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "42280s"},
                    ]
                )
                with patch.object(summarize.genai, "Client", return_value=client), patch.object(
                    summarize.time, "sleep"
                ) as sleep:
                    result = self.summarize()
                self.assertFalse(result["retryable"])
                self.assertTrue(result["degraded"])
                client.models.generate_content.assert_called_once()
                sleep.assert_not_called()

    def test_transient_errors_still_retry_and_recover(self):
        for failure in (
            api_error(503, "Model overloaded"),
            api_error(408, "Request timeout"),
            api_error(429, "Rate limit exceeded", [{
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}],
            }]),
        ):
            with self.subTest(code=failure.code):
                client = Mock()
                client.models.generate_content.side_effect = [failure, GOOD_RESPONSE]
                with patch.object(summarize.genai, "Client", return_value=client), patch.object(
                    summarize.time, "sleep"
                ) as sleep:
                    result = self.summarize()
                self.assertEqual(result["picks"][0]["pick"], "Boston ML")
                self.assertEqual(client.models.generate_content.call_count, 2)
                sleep.assert_called_once()

    def test_invalid_json_still_retries(self):
        client = Mock()
        client.models.generate_content.side_effect = [
            SimpleNamespace(text="broken JSON"), GOOD_RESPONSE
        ]
        with patch.object(summarize.genai, "Client", return_value=client), patch.object(
            summarize.time, "sleep"
        ):
            result = self.summarize()
        self.assertEqual(result["picks"][0]["pick"], "Boston ML")
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_no_source_content_does_not_call_gemini(self):
        with patch.object(summarize.genai, "Client") as factory:
            result = summarize.summarize_with_gemini(None, None, "Channel", "Title")
        self.assertTrue(result["degraded"])
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
