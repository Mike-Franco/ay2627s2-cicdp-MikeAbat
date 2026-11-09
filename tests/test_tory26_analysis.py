from django.test import SimpleTestCase

from scripts.tory26_analyze import CLASSES, DEPENDENT, ORDINARY, analyze, nearest_rank_p95
from scripts.tory26_http_benchmark import InvalidRun, sample_class


def sample_evidence():
    return {
        "runs": [{
            "warmups": {name: [0.1] * 20 for name in CLASSES},
            "measurements": {
                **{name: [1.0] * 100 for name in ORDINARY},
                **{name: [2.0] * 500 for name in DEPENDENT},
            },
        } for _ in range(3)],
        "csv": {"valid_rows": 1000, "seconds": 29.9},
    }


class Tory26AnalysisTests(SimpleTestCase):
    def test_rejected_sample_invalidates_whole_run_without_retry(self):
        class Client:
            def __init__(self):
                self.calls = 0

            def timed(self, kind):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError(f"{kind} returned HTTP 429, expected 302")
                return 0.1

        clients = [Client() for _ in range(5)]
        with self.assertRaises(InvalidRun) as caught:
            sample_class("login", clients, 5)
        self.assertEqual(sum(client.calls for client in clients), 5)
        self.assertEqual(caught.exception.failures[0]["sample"], 1)
        self.assertIn("HTTP 429", caught.exception.failures[0]["error"])

        evidence = sample_evidence()
        evidence["invalid_run"] = {"run": 2, "failures": caught.exception.failures}
        with self.assertRaisesRegex(ValueError, "invalidated a complete run"):
            analyze(evidence)

    def test_nearest_rank_uses_the_475th_of_500(self):
        self.assertEqual(nearest_rank_p95([1.98] * 475 + [2.4] * 25), 1.98)

    def test_each_run_must_pass_independently(self):
        evidence = sample_evidence()
        evidence["runs"][2]["measurements"]["login"] = [2.1] * 100
        result = analyze(evidence)
        self.assertTrue(result["runs"][0]["ordinary_pass"])
        self.assertFalse(result["runs"][2]["ordinary_pass"])
        self.assertFalse(result["timing_thresholds_met"])

    def test_missing_class_or_wrong_sample_count_is_rejected(self):
        evidence = sample_evidence()
        del evidence["runs"][0]["measurements"]["inventory_products"]
        with self.assertRaisesRegex(ValueError, "six approved route classes"):
            analyze(evidence)
        evidence = sample_evidence()
        evidence["runs"][0]["warmups"]["inventory_view"].pop()
        with self.assertRaisesRegex(ValueError, "20 durations"):
            analyze(evidence)
