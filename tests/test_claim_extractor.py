import unittest

from app.services.claim_extractor import extract_candidate_claims


class ClaimExtractorTests(unittest.TestCase):
    def test_extracts_measurable_claim(self):
        text = (
            "The agency reported that enrollment increased by 18% in 2025 compared with the prior year. "
            "This is a purely subjective sentence about what should happen next."
        )
        claims = extract_candidate_claims(text)
        self.assertGreaterEqual(len(claims), 1)
        self.assertIn("18%", claims[0]["text"])
        self.assertEqual(claims[0]["status"], "unresolved")

    def test_does_not_claim_truth(self):
        text = "Officials said the project cost $4.6 billion in 2025 and served 1,240,000 people."
        claims = extract_candidate_claims(text)
        self.assertTrue(all(c["status"] == "unresolved" for c in claims))

    def test_filters_newsletter_and_navigation_boilerplate(self):
        text = (
            "SIGN UP TO GET THE POLITICS NEWSLETTER. "
            "The poll indicates that 96% of Republicans backed the candidate."
        )
        claims = extract_candidate_claims(text)
        self.assertEqual(len(claims), 1)
        self.assertIn("96%", claims[0]["text"])
        self.assertNotIn("NEWSLETTER", claims[0]["text"])

    def test_filters_date_fragment(self):
        text = (
            "5, 2026, after narrowly winning the nomination. "
            "Officials reported that turnout increased by 12% in 2026."
        )
        claims = extract_candidate_claims(text)
        self.assertTrue(all(not c["text"].startswith("5, 2026") for c in claims))
        self.assertTrue(any("12%" in c["text"] for c in claims))

    def test_opinion_only_statement_is_not_promoted_as_fact(self):
        text = "I believe this is the worst political strategy and should never be repeated."
        claims = extract_candidate_claims(text)
        self.assertEqual(claims, [])


if __name__ == "__main__":
    unittest.main()
