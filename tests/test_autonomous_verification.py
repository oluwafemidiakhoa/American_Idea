import unittest
from unittest.mock import patch

from app.services.autonomous_verification import _discovery_context, _matrix, autonomously_verify_claim


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

    def test_context_envelope_uses_title_source_and_neighbours(self):
        record = {
            "title": "Moderna, Merck breakthrough could usher in wave of cancer vaccines",
            "source_name": "CNN",
            "claims": [
                {"id": "before", "text": "The companies said they saw no new side effects with the addition of the vaccine."},
                {"id": "target", "text": "What we saw in the mid-stage trial were reactions like a flu or COVID shot, Hoge said."},
                {"id": "after", "text": "Doctors are evaluating the vaccine with Keytruda in melanoma."},
            ],
        }
        context = _discovery_context(record, "target")
        joined = " ".join(context["components"])
        self.assertIn("Moderna", joined)
        self.assertIn("CNN", joined)
        self.assertIn("Keytruda", joined)
        self.assertIn("side effects", joined)

    @patch("app.services.autonomous_verification.save_verification", return_value=0)
    @patch("app.services.autonomous_verification.verify_claim_evidence")
    @patch("app.services.autonomous_verification.save_discovery_leads", return_value=1)
    @patch("app.services.autonomous_verification.discover_with_provider_plans")
    @patch("app.services.autonomous_verification.get_record")
    def test_context_improves_discovery_but_verification_uses_exact_claim(
        self,
        get_record,
        discover,
        save_leads,
        verify,
        save_verification,
    ):
        exact = "What we saw in the mid-stage trial were reactions like a flu or COVID shot, Hoge said."
        claim = {"id": "target", "text": exact, "status": "unresolved", "confidence": 0.35, "evidence": []}
        record = {
            "record_id": "ai_12345678",
            "title": "Moderna, Merck breakthrough could usher in wave of cancer vaccines",
            "source_name": "CNN",
            "article_url": "https://publisher.example/story",
            "claims": [
                {"id": "before", "text": "The companies said they saw no new side effects with the vaccine.", "evidence": []},
                claim,
                {"id": "after", "text": "The melanoma vaccine is being studied with Keytruda.", "evidence": []},
            ],
        }
        refreshed_claim = {**claim, "evidence": [{"kind": "primary", "label": "trial", "url": "https://clinicaltrials.gov/study/NCT1", "fetch_status": "not_fetched", "relation": "unverified_lead", "verification_confidence": 0}]}
        refreshed = {**record, "claims": [record["claims"][0], refreshed_claim, record["claims"][2]]}
        get_record.side_effect = [record, refreshed, refreshed]
        discover.return_value = {
            "domain_profile": "life_science",
            "queries": ["Moderna Merck melanoma vaccine"],
            "provider_query_plan": {"clinicaltrials_gov": ["Moderna Merck melanoma"]},
            "leads": [{"kind": "primary", "title": "trial", "url": "https://clinicaltrials.gov/study/NCT1"}],
        }
        verify.return_value = ([refreshed_claim], 1, 1)

        result = autonomously_verify_claim(record_id="ai_12345678", claim_id="target")

        self.assertEqual(discover.call_args.args[0], exact)
        anchors = discover.call_args.kwargs["retrieval_anchors"]
        self.assertIn("Moderna", anchors)
        self.assertIn("Keytruda", anchors)
        verification_claim = verify.call_args.args[0][0]
        self.assertEqual(verification_claim["text"], exact)
        self.assertTrue(result["discovery_context"])

    @patch("app.services.autonomous_verification.save_verification", return_value=0)
    @patch("app.services.autonomous_verification.verify_claim_evidence")
    @patch("app.services.autonomous_verification.save_discovery_leads", return_value=1)
    @patch("app.services.autonomous_verification.discover_with_provider_plans")
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
            "provider_query_plan": {"gdelt": ["test public result 2026"]},
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
