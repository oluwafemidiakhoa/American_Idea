import unittest

from app.services.source_intelligence import classify_claim_domain, source_profile_for_claim
from app.services.trust_gate import evaluate_claim_trust, enforce_claim_trust


class SourceIntelligenceTests(unittest.TestCase):
    def test_general_news_has_fallback_profile(self):
        self.assertEqual(classify_claim_domain("A city council member announced a new downtown proposal."), "general")
        profile = source_profile_for_claim("A city council member announced a new downtown proposal.")
        self.assertEqual(profile.name, "general")
        self.assertFalse(profile.use_federal_register)

    def test_regulatory_general_news_can_route_federal_register(self):
        profile = source_profile_for_claim("The agency published a final rule in the Federal Register changing federal policy.")
        self.assertTrue(profile.use_federal_register)

    def test_life_science_routes_to_trial_and_health_sources(self):
        profile = source_profile_for_claim("Moderna said its Phase 3 melanoma vaccine trial met its endpoint.")
        self.assertEqual(profile.name, "life_science")
        self.assertTrue(profile.use_clinical_trials)
        self.assertIn("fda.gov", profile.official_domains)
        self.assertIn("modernatx.com", profile.official_domains)

    def test_finance_routes_to_sec(self):
        profile = source_profile_for_claim("The company reported quarterly revenue and filed an 8-K with the SEC.")
        self.assertEqual(profile.name, "finance_business")
        self.assertIn("sec.gov", profile.official_domains)

    def test_election_routes_to_election_authorities(self):
        profile = source_profile_for_claim("Officials certified the election results after the recount.")
        self.assertEqual(profile.name, "elections")
        self.assertIn("eac.gov", profile.official_domains)


class TrustGateTests(unittest.TestCase):
    def _evidence(self, *, kind="secondary", relation="supports", confidence=0.9, url="https://example.com/a"):
        return {
            "kind": kind,
            "relation": relation,
            "verification_confidence": confidence,
            "fetch_status": "verified",
            "url": url,
        }

    def test_single_secondary_cannot_be_supported(self):
        claim = {"status": "supported", "evidence": [self._evidence()]}
        audit = evaluate_claim_trust(claim)
        self.assertFalse(audit["passed"])
        self.assertEqual(audit["public_status"], "unresolved")

    def test_supported_requires_primary_and_independent_support(self):
        claim = {
            "status": "supported",
            "evidence": [
                self._evidence(kind="primary", confidence=0.90, url="https://agency.gov/record"),
                self._evidence(kind="secondary", confidence=0.87, url="https://independent.example/report"),
            ],
        }
        audit = evaluate_claim_trust(claim)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["public_status"], "supported")

    def test_contradiction_blocks_simple_supported_status(self):
        claim = {
            "status": "supported",
            "evidence": [
                self._evidence(kind="primary", confidence=0.90, url="https://agency.gov/record"),
                self._evidence(kind="secondary", confidence=0.88, url="https://independent.example/report"),
                self._evidence(kind="secondary", relation="contradicts", confidence=0.86, url="https://other.example/counter"),
            ],
        }
        enforced = enforce_claim_trust(claim)
        self.assertEqual(enforced["status"], "unresolved")
        self.assertIn("Trust Gate blocked", enforced["status_basis"])

    def test_failed_source_is_counted_but_not_evidence(self):
        claim = {
            "status": "unresolved",
            "evidence": [{
                "kind": "secondary",
                "relation": "unverified_lead",
                "verification_confidence": 0,
                "fetch_status": "fetch_failed",
                "url": "https://blocked.example/story",
            }],
        }
        audit = evaluate_claim_trust(claim)
        self.assertEqual(audit["failed_or_blocked_count"], 1)
        self.assertEqual(audit["verified_source_count"], 0)


if __name__ == "__main__":
    unittest.main()
