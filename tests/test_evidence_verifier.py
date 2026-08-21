import unittest

from app.services.evidence_verifier import classify_evidence_passage, derive_claim_status


class EvidenceVerifierTests(unittest.TestCase):
    def test_numeric_primary_passage_can_support(self):
        claim = "The ship is not expected to be delivered until 2034."
        passage = "The carrier is now expected to be delivered in 2034 because of shipbuilder constraints."
        match = classify_evidence_passage(claim, passage)
        self.assertEqual(match.relation, "supports")
        self.assertGreaterEqual(match.confidence, 0.78)

    def test_negation_difference_can_contradict(self):
        claim = "Officials said the program did not reduce processing time."
        passage = "Officials said the program reduced processing time by 30 percent."
        match = classify_evidence_passage(claim, passage)
        self.assertEqual(match.relation, "contradicts")

    def test_weak_overlap_only_contextualizes_or_mentions(self):
        claim = "The Navy renamed the carrier in 2026."
        passage = "The Navy described the history of aircraft carrier naming conventions."
        match = classify_evidence_passage(claim, passage)
        self.assertIn(match.relation, {"contextualizes", "mentions"})

    def test_single_primary_support_is_only_partial(self):
        claim = {
            "evidence": [
                {
                    "kind": "primary",
                    "url": "https://navy.mil/example",
                    "fetch_status": "verified",
                    "relation": "supports",
                    "verification_confidence": 0.90,
                }
            ]
        }
        status, _ = derive_claim_status(claim)
        self.assertEqual(status, "partially_supported")

    def test_primary_plus_independent_support_can_be_supported(self):
        claim = {
            "evidence": [
                {
                    "kind": "primary",
                    "url": "https://navy.mil/example",
                    "fetch_status": "verified",
                    "relation": "supports",
                    "verification_confidence": 0.90,
                },
                {
                    "kind": "secondary",
                    "url": "https://example.org/report",
                    "fetch_status": "verified",
                    "relation": "supports",
                    "verification_confidence": 0.86,
                },
            ]
        }
        status, _ = derive_claim_status(claim)
        self.assertEqual(status, "supported")

    def test_conflicting_strong_evidence_is_contested(self):
        claim = {
            "evidence": [
                {
                    "kind": "primary",
                    "url": "https://agency.gov/a",
                    "fetch_status": "verified",
                    "relation": "supports",
                    "verification_confidence": 0.90,
                },
                {
                    "kind": "secondary",
                    "url": "https://example.org/b",
                    "fetch_status": "verified",
                    "relation": "contradicts",
                    "verification_confidence": 0.88,
                },
            ]
        }
        status, _ = derive_claim_status(claim)
        self.assertEqual(status, "contested")


if __name__ == "__main__":
    unittest.main()
