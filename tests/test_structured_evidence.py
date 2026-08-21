import unittest
from unittest.mock import Mock, patch

from app.services.source_intelligence import source_profile_for_claim
from app.services.structured_source_ingestor import ingest_clinical_trial, ingest_pubmed


class StructuredEvidenceTests(unittest.TestCase):
    def test_life_science_does_not_route_federal_register_by_default(self):
        profile = source_profile_for_claim(
            "Merck and Moderna reported a melanoma vaccine result from a Phase 3 clinical trial."
        )
        self.assertEqual(profile.name, "life_science")
        self.assertTrue(profile.use_clinical_trials)
        self.assertTrue(profile.use_pubmed)
        self.assertFalse(profile.use_federal_register)

    @patch("app.services.structured_source_ingestor.httpx.get")
    def test_clinical_trials_url_uses_structured_api(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT03897881",
                    "officialTitle": "Personalized Cancer Vaccine mRNA-4157 and Pembrolizumab in High-Risk Melanoma",
                },
                "statusModule": {"overallStatus": "COMPLETED"},
                "designModule": {
                    "phases": ["PHASE2"],
                    "enrollmentInfo": {"count": 157, "type": "ACTUAL"},
                },
                "conditionsModule": {"conditions": ["Melanoma"]},
                "armsInterventionsModule": {
                    "interventions": [
                        {"name": "mRNA-4157"},
                        {"name": "Pembrolizumab"},
                    ]
                },
                "outcomesModule": {
                    "primaryOutcomes": [
                        {"measure": "Recurrence-free survival", "timeFrame": "Up to 3 years"}
                    ]
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "ModernaTX, Inc."},
                    "collaborators": [{"name": "Merck Sharp & Dohme LLC"}],
                },
            }
        }
        get.return_value = response

        article = ingest_clinical_trial("https://clinicaltrials.gov/study/NCT03897881")

        self.assertIn("NCT03897881", article.text)
        self.assertIn("mRNA-4157", article.text)
        self.assertIn("Merck", article.text)
        self.assertEqual(article.content_type, "application/json")
        self.assertTrue(article.content_sha256)

    @patch("app.services.structured_source_ingestor.httpx.get")
    def test_pubmed_url_uses_structured_record_and_abstract(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = """
        <PubmedArticleSet><PubmedArticle><MedlineCitation><Article>
          <ArticleTitle>Individualised neoantigen therapy in melanoma</ArticleTitle>
          <Abstract><AbstractText Label='BACKGROUND'>Melanoma trial background.</AbstractText>
          <AbstractText Label='RESULTS'>Recurrence-free survival was evaluated.</AbstractText></Abstract>
          <Journal><Title>Example Journal</Title></Journal>
          <AuthorList><Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author></AuthorList>
        </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>
        """
        get.return_value = response

        article = ingest_pubmed("https://pubmed.ncbi.nlm.nih.gov/12345678/")

        self.assertIn("Recurrence-free survival", article.text)
        self.assertIn("Example Journal", article.text)
        self.assertEqual(article.content_type, "application/xml")


if __name__ == "__main__":
    unittest.main()
