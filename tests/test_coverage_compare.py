import unittest

from app.services.coverage_compare import claim_similarity, compare_records


class CoverageCompareTests(unittest.TestCase):
    def test_similar_claims_cluster(self):
        left = "The carrier is expected to be delivered in 2034."
        right = "Delivery of the aircraft carrier is now expected in 2034."
        self.assertGreaterEqual(claim_similarity(left, right), 0.56)

    def test_conflicting_years_are_penalized(self):
        left = "The carrier is expected to be delivered in 2034."
        right = "The carrier is expected to be delivered in 2031."
        self.assertLess(claim_similarity(left, right), 0.56)

    def test_compare_marks_shared_and_source_specific(self):
        records = [
            {
                "record_id": "ai_one",
                "source_name": "Outlet One",
                "article_url": "https://one.example/story",
                "claims": [
                    {"id": "claim_a", "text": "The carrier is expected to be delivered in 2034.", "status": "unresolved", "confidence": 0.7},
                    {"id": "claim_b", "text": "The program cost $4.6 billion in 2025.", "status": "unresolved", "confidence": 0.8},
                ],
            },
            {
                "record_id": "ai_two",
                "source_name": "Outlet Two",
                "article_url": "https://two.example/story",
                "claims": [
                    {"id": "claim_c", "text": "Delivery of the aircraft carrier is now expected in 2034.", "status": "unresolved", "confidence": 0.7},
                ],
            },
        ]
        result = compare_records(records)
        classifications = [cluster["classification"] for cluster in result["clusters"]]
        self.assertIn("shared", classifications)
        self.assertIn("source_specific", classifications)

    def test_status_disagreement_is_visible(self):
        records = [
            {"record_id": "ai_one", "source_name": "One", "claims": [{"id": "a", "text": "The agency reported 1 million enrollments in 2025.", "status": "supported"}]},
            {"record_id": "ai_two", "source_name": "Two", "claims": [{"id": "b", "text": "The agency reported 1 million enrollments during 2025.", "status": "unsupported"}]},
        ]
        result = compare_records(records)
        shared = next(cluster for cluster in result["clusters"] if cluster["classification"] == "shared")
        self.assertTrue(shared["status_disagreement"])


if __name__ == "__main__":
    unittest.main()
