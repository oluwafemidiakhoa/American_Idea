import unittest

from app.services.evidence_discovery import DiscoveryLead
from app.services.provider_discovery import _relevance
from app.services.provider_query_planner import build_provider_query_plan
from app.services.source_intelligence import source_profile_for_claim


class GeopoliticsProviderRoutingTests(unittest.TestCase):
    def test_search_query_does_not_inflate_irrelevant_source_relevance(self):
        claim = "Iranian president says it is time to end the war and criticizes radicals."
        lead = DiscoveryLead(
            provider="federal_register",
            kind="primary",
            title="Medicare and Medicaid Programs; CY 2027 Payment Policies",
            url="https://www.federalregister.gov/example",
            source_name="Federal Register",
            query="Iranian president end war radicals",
        )
        self.assertEqual(_relevance(lead, claim), 0.0)

    def test_geopolitics_query_plan_never_routes_federal_register(self):
        claim = "Iranian president says it is time to end the war and criticizes radicals."
        profile = source_profile_for_claim(claim)
        plan = build_provider_query_plan(
            claim,
            profile_name=profile.name,
            retrieval_anchors=["Live Updates Fox News Digital", "sanctions", "Iran"],
        )
        self.assertEqual(profile.name, "geopolitics_conflict")
        self.assertEqual(plan["federal_register"], [])
        joined = " ".join(plan["gdelt"]).lower()
        self.assertIn("iran", joined)
        self.assertIn("war", joined)
        self.assertNotIn("fox news", joined)


if __name__ == "__main__":
    unittest.main()
