"""Preserve report guardrails while avoiding retries for permanent Gemini errors."""

import unittest
from unittest.mock import patch

import main


def channel_result(status, name="Test Channel", retryable=True):
    result = {
        "channel_name": name,
        "video": {"title": "NBA Picks", "url": "https://youtu.be/test"},
        "transcript": "I like Boston ML.",
        "scraped_picks": None,
        "summary": {"picks": [{"pick": "Boston ML"}]},
        "error": None,
    }
    if status == "EMPTY":
        result["error"] = "No fresh video found for today."
    elif status == "DEGRADED":
        result["summary"] = {
            "picks": [],
            "degraded": "Temporary Gemini failure" if retryable else "Daily Gemini quota exhausted",
            "retryable": retryable,
        }
    return result


class ChannelRetryTests(unittest.TestCase):
    spec = {"channel_label": "TEST"}

    def test_permanent_degradation_skips_full_pipeline_retries(self):
        result = channel_result("DEGRADED", retryable=False)
        with patch.object(main, "_process_channel", return_value=result) as process, patch.object(
            main.time, "sleep"
        ) as sleep:
            self.assertIs(main._process_channel_resilient(self.spec), result)
        process.assert_called_once()
        sleep.assert_not_called()

    def test_transient_degradation_retries_then_recovers(self):
        good = channel_result("OK")
        with patch.object(
            main, "_process_channel", side_effect=[channel_result("DEGRADED"), good]
        ) as process, patch.object(main.time, "sleep") as sleep:
            self.assertIs(main._process_channel_resilient(self.spec), good)
        self.assertEqual(process.call_count, 2)
        sleep.assert_called_once()

    def test_transient_degradation_has_bounded_attempts(self):
        with patch.object(
            main, "_process_channel", return_value=channel_result("DEGRADED")
        ) as process, patch.object(main.time, "sleep") as sleep:
            main._process_channel_resilient(self.spec)
        self.assertEqual(process.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_malformed_summary_can_retry_and_recover(self):
        broken = channel_result("OK")
        broken["summary"] = "invalid summary"
        good = channel_result("OK")
        with patch.object(
            main, "_process_channel", side_effect=[broken, good]
        ) as process, patch.object(main.time, "sleep"):
            self.assertIs(main._process_channel_resilient(self.spec), good)
        self.assertEqual(process.call_count, 2)


class ReportGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.secrets = patch.object(main, "_check_secrets")
        self.secrets.start()
        self.addCleanup(self.secrets.stop)

    def test_all_empty_is_clean_noop(self):
        with patch.object(
            main, "_process_channel_resilient", side_effect=[channel_result("EMPTY"), channel_result("EMPTY")]
        ), patch.object(main, "send_email") as send, patch.object(main, "build_report") as build:
            with self.assertRaises(SystemExit) as exc:
                main.main()
        self.assertEqual(exc.exception.code, 0)
        build.assert_not_called()
        send.assert_not_called()

    def test_all_degraded_fails_without_sending(self):
        with patch.object(
            main, "_process_channel_resilient", side_effect=[channel_result("DEGRADED"), channel_result("DEGRADED")]
        ), patch.object(main, "send_email") as send, patch.object(main, "build_report") as build:
            with self.assertRaises(SystemExit) as exc:
                main.main()
        self.assertEqual(exc.exception.code, 1)
        build.assert_not_called()
        send.assert_not_called()

    def test_one_healthy_source_sends_and_lists_skipped_source(self):
        good = channel_result("OK", name="Good")
        degraded = channel_result("DEGRADED", name="Unavailable", retryable=False)
        with patch.object(
            main, "_process_channel_resilient", side_effect=[good, degraded]
        ), patch.object(main, "build_report", return_value=("subject", "text", "html")) as build, patch.object(
            main, "send_email"
        ) as send:
            main.main()
        build.assert_called_once_with([good], [("Unavailable", "Daily Gemini quota exhausted")])
        send.assert_called_once_with("subject", "text", "html")

    def test_dry_run_builds_report_without_sending(self):
        good = channel_result("OK")
        with patch.object(main, "_process_channel_resilient", return_value=good), patch.object(
            main, "build_report", return_value=("subject", "text", "html")
        ) as build, patch.object(main, "send_email") as send:
            main.main(dry_run=True)
        build.assert_called_once()
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
