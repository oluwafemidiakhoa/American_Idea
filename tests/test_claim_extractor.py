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

    def test_subjective_attributed_quote_is_not_promoted(self):
        text = '“It is a big deal for the field in general,” said Dr. Jane Example, an oncology researcher.'
        claims = extract_candidate_claims(text)
        self.assertEqual(claims, [])

    def test_dr_abbreviation_does_not_create_broken_claim(self):
        text = (
            '“It is a big deal for the field in general,” said Dr. Jane Example. '
            'The companies reported that 1,000 patients were enrolled in the trial.'
        )
        claims = extract_candidate_claims(text)
        self.assertTrue(all(not c["text"].endswith("said Dr.") for c in claims))
        self.assertTrue(any("1,000 patients" in c["text"] for c in claims))

    def test_bare_future_year_is_not_a_measurable_quantity(self):
        text = "The senator is now in the conversation for the 2028 presidential race."
        claims = extract_candidate_claims(text)
        self.assertEqual(claims, [])

    def test_filters_photo_caption(self):
        text = (
            "Jon Ossoff speaks to members of the media during the opening of a field office in Decatur May 23, 2026. "
            "(Elijah Nouvelage/Bloomberg via Getty Images)\n\n"
            "The campaign reported that the clip received over 6 million views on X."
        )
        claims = extract_candidate_claims(text)
        self.assertTrue(any("6 million views" in c["text"] for c in claims))
        self.assertTrue(all("Getty Images" not in c["text"] for c in claims))

    def test_strips_media_filename_prefix(self):
        text = (
            "31677919125902354649540948202559193_00000001.jpg A waterspout came ashore in Nassau County Thursday evening, "
            "significantly damaging cabanas and buildings, the club said."
        )
        claims = extract_candidate_claims(text)
        self.assertTrue(claims)
        self.assertTrue(all(".jpg" not in c["text"] for c in claims))
        self.assertTrue(any(c["text"].startswith("A waterspout") for c in claims))

    def test_strips_social_photo_credit_prefix(self):
        text = (
            "Caitlin Harvey/ Facebook Significant damage including flooding and downed trees was reported throughout Dover, "
            "Delaware, after a likely tornado hit the city, according to the Dover Police Department."
        )
        claims = extract_candidate_claims(text)
        self.assertTrue(claims)
        self.assertTrue(all("Caitlin Harvey" not in c["text"] for c in claims))
        self.assertTrue(any(c["text"].startswith("Significant damage") for c in claims))


if __name__ == "__main__":
    unittest.main()
