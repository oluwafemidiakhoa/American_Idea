import unittest
from app.services.claim_extractor import extract_candidate_claims

class ClaimExtractorTests(unittest.TestCase):
    def test_extracts_measurable_claim(self):
        text = "The agency reported that enrollment increased by 18% in 2025 compared with the prior year. This is a purely subjective sentence about what should happen next."
        claims = extract_candidate_claims(text)
        self.assertGreaterEqual(len(claims), 1)
        self.assertIn("18%", claims[0]["text"])
        self.assertEqual(claims[0]["status"], "unresolved")

    def test_does_not_claim_truth(self):
        text = "Officials said the project cost $4.6 billion in 2025 and served 1,240,000 people."
        claims = extract_candidate_claims(text)
        self.assertTrue(all(c["status"] == "unresolved" for c in claims))

if __name__ == "__main__":
    unittest.main()
