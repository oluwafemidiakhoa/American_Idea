import unittest
from unittest.mock import patch

from app.services.evidence_discovery import DiscoveryLead, discover_evidence_for_claim
from app.services.source_intelligence import source_profile_for_claim


class DirectSourceAdapterTests(unittest.TestCase):
    def test_life_science_profile_enables_pubmed(self):
        profile = source_profile_for_claim("A melanoma vaccine Phase 3 clinical trial reported new results.")
        self.assertEqual(profile.name, "life_science")
        self.assertTrue(profile.use_pubmed)
        self.assertTrue(profile.use_clinical_trials)

    @patch("app.services.evidence_discovery.discover_gdelt", return_value=[])
    @patch("app.services.evidence_discovery.discover_official_domain", return_value=[])
    @patch("app.services.evidence_discovery.discover_federal_register", return_value=[])
    @patch("app.services.evidence_discovery.discover_pubmed")
    @patch("app.services.evidence_discovery.discover_clinical_trials", return_value=[])
    def test_diagnostics_report_pubmed_results(
        self,
        clinical_trials,
        pubmed,
        federal_register,
        official_domain,
        gdelt,
    ):
        pubmed.return_value = [
            DiscoveryLead(
                provider="pubmed",
                kind="secondary",
                title="A melanoma vaccine study",
                url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
                source_name="Example Journal",
                query="melanoma vaccine",
            )
        ]

        result = discover_evidence_for_claim(
            "A melanoma vaccine clinical trial reported results.",
            article_url="https://news.example/story",
            max_results=8,
        )

        self.assertEqual(result["domain_profile"], "life_science")
        self.assertIn("pubmed", result["providers_used"])
        self.assertTrue(result["provider_diagnostics"]["pubmed"]["attempted"])
        self.assertGreaterEqual(result["provider_diagnostics"]["pubmed"]["result_count"], 1)
        self.assertEqual(result["provider_diagnostics"]["pubmed"]["status"], "results")

    @patch("app.services.evidence_discovery.discover_gdelt", return_value=[])
    @patch("app.services.evidence_discovery.discover_official_domain", return_value=[])
    @patch("app.services.evidence_discovery.discover_federal_register", return_value=[])
    def test_general_profile_keeps_broad_fallback(self, federal_register, official_domain, gdelt):
        result = discover_evidence_for_claim(
            "A city council member announced a downtown proposal.",
            article_url="https://local.example/story",
            max_results=8,
        )
        self.assertEqual(result["domain_profile"], "general")
        self.assertTrue(result["provider_diagnostics"]["gdelt"]["attempted"])
        self.assertFalse(result["provider_diagnostics"]["pubmed"]["attempted"])
        self.assertEqual(result["provider_diagnostics"]["pubmed"]["status"], "not_routed")


if __name__ == "__main__":
    unittest.main()
