import unittest

from app.services.ledger import evidence_public_id, story_public_id


class LedgerIdentifierTests(unittest.TestCase):
    def test_story_id_is_stable_from_content_hash(self):
        digest = "abcdef0123456789" * 4
        self.assertEqual(story_public_id(digest), "ai_abcdef0123456789")
        self.assertEqual(story_public_id(digest), story_public_id(digest))

    def test_evidence_id_is_deterministic(self):
        first = evidence_public_id(
            "claim_123",
            "https://agency.gov/report",
            "Agency report",
        )
        second = evidence_public_id(
            "claim_123",
            "https://agency.gov/report",
            "Agency report",
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("ev_"))

    def test_evidence_id_changes_with_source(self):
        one = evidence_public_id("claim_123", "https://agency.gov/a", "Report")
        two = evidence_public_id("claim_123", "https://agency.gov/b", "Report")
        self.assertNotEqual(one, two)


if __name__ == "__main__":
    unittest.main()
