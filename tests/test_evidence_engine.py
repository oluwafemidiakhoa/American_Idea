import unittest

from app.services.evidence_engine import assess_evidence_candidate


class EvidenceEngineTests(unittest.TestCase):
    def test_primary_hashed_evidence_scores_high_but_does_not_decide_truth(self):
        result = assess_evidence_candidate(
            claim_id="claim_123456789abc",
            label="Official election results",
            url="https://example.gov/results",
            kind="primary",
            relation="supports",
            source_type="government",
            directness=1.0,
            independence=0.9,
            has_capture_hash=True,
        )
        self.assertGreaterEqual(result["quality_score"], 0.9)
        self.assertEqual(result["claim_status"], "unresolved")
        self.assertTrue(result["review_required"])

    def test_mention_without_provenance_is_capped_and_warned(self):
        result = assess_evidence_candidate(
            claim_id="claim_123456789abc",
            label="Secondary article mention",
            url=None,
            kind="secondary",
            relation="mentions",
            source_type="news",
            directness=0.3,
            independence=0.4,
            has_capture_hash=False,
        )
        self.assertLessEqual(result["quality_score"], 0.6)
        self.assertGreaterEqual(len(result["warnings"]), 2)
        self.assertEqual(result["claim_status"], "unresolved")

    def test_evidence_id_is_deterministic(self):
        kwargs = dict(
            claim_id="claim_abcdef123456",
            label="Court filing",
            url="https://example.gov/filing",
            kind="primary",
            relation="supports",
            source_type="court",
            directness=0.8,
            independence=1.0,
            has_capture_hash=True,
        )
        first = assess_evidence_candidate(**kwargs)
        second = assess_evidence_candidate(**kwargs)
        self.assertEqual(first["evidence_id"], second["evidence_id"])


if __name__ == "__main__":
    unittest.main()
