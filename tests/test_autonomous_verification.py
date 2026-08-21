import unittest
from unittest.mock import patch

from app.services.autonomous_verification import _matrix, autonomously_verify_claim


class AutonomousVerificationTests(unittest.TestCase):
    def test_matrix_separates_verified_failed_and_unverified(self):
        claim = {
            "id": "claim_1",
            "status": "unresolved",
            "status_basis": "Not enough evidence.",
            "evidence": [
                {"kind": "primary", "url": "https://agency.gov/a", "fetch_status": "verified", "relation": "supports", "verification_confidence": 0.88},
                {"kind": "secondary", "url": "https://news.example/a", "fetch_status": "fetch_failed", "relation": "unverified_lead", "verification_confidence": 0},
                {"kind": "secondary", "url": "https://other.example/a", "fetch_status": "not_fetched", "relation": "unverified_lead", "verification_confidence": 0},
            ],
        }
        matrix = _matrix(claim)
        self.assertEqual(matrix["verified_source_count"], 1)
        self.assertEqual(matrix["verified_primary_count"], 1)
        self.assertEqual(matrix["blocked_or_failed_count"], 1)
        self.assertEqual(matrix["unverified_lead_count"], 2)
        self.assertEqual(matrix["strongest_support"], 0.88)

    @patch("app.services.autonomous_verification.save_verification", return_value=0)
    @patch("app.services.autonomous_verification.verify_claim_evidence")
    @patch("app.services.autonomous_verification.save_discovery_leads", return_value=1)
    @patch("app.services.autonomous_verification.discover_evidence_for_claim")
    @patch("app.services.autonomous_verification.get_record")
    def test_failed_url_is_not_retried_in_new_fetch_budget(
        self,
        get_record,
        discover,
        save_leads,
        verify,
        save_verification,
    ):
        record = {
            "record_id": "ai_12345678",
            "article_url": "https://publisher.example/story",
            "claims": [{
                "id": "claim_1",
                "text": "A test claim about a public result in 2026.",
                "status": "unresolved",
                "confidence": 0.5,
                "evidence": [{
                    "kind": "secondary",
                    "label": "blocked",
                    "url": "https://blocked.example/story",
                    "fetch_status": "fetch_failed",
                    "relation": "unverified_lead",
                    "verification_confidence": 0,
                }],
            }],
        }
        refreshed = {
            **record,
            "claims": [{
                **record["claims"][0],
                "evidence": record["claims"][0]["evidence"] + [{
                    "kind": "primary",
                    "label": "official",
                    "url": "https://agency.gov/record",
                    "fetch_status": "not_fetched",
                    "relation": "unverified_lead",
                    "verification_confidence": 0,
                }],
            }],
        }
        updated = refreshed
        get_record.side_effect = [record, refreshed, updated]
        discover.return_value = {
            "queries": ["test public result 2026"],
            "leads": [
                {"kind": "secondary", "title": "blocked again", "url": "https://blocked.example/story"},
                {"kind": "primary", "title": "official", "url": "https://agency.gov/record"},
            ],
        }
        verify.return_value = ([refreshed["claims"][0]], 1, 1)

        autonomously_verify_claim(record_id="ai_12345678", claim_id="claim_1")

        saved = save_leads.call_args.kwargs["leads"]
        self.assertEqual([item["url"] for item in saved], ["https://agency.gov/record"])
        verification_input = verify.call_args.args[0][0]["evidence"]
        self.assertNotIn("https://blocked.example/story", [item.get("url") for item in verification_input])


if __name__ == "__main__":
    unittest.main()
