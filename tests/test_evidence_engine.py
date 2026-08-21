import unittest

from app.services.evidence_engine import attach_source_link_evidence
from app.services.url_ingestor import ArticleBlock, ArticleLink


class EvidenceEngineTests(unittest.TestCase):
    def test_attaches_government_link_as_primary_lead(self):
        claims = [
            {
                "id": "claim_1",
                "text": "The Navy announced that the carrier would be named for Doris Miller in 2020.",
                "status": "unresolved",
                "confidence": 0.45,
                "why_flagged": ["contains an attributed or externally verifiable assertion"],
                "evidence": [],
            }
        ]
        blocks = [
            ArticleBlock(
                text="The Navy announced that the carrier would be named for Doris Miller in 2020.",
                links=[ArticleLink(text="Navy release", url="https://www.navy.mil/Press-Office/News-Stories/")],
            )
        ]

        enriched = attach_source_link_evidence(claims, blocks, "https://www.cnn.com/example")
        self.assertEqual(len(enriched[0]["evidence"]), 1)
        self.assertEqual(enriched[0]["evidence"][0]["kind"], "primary")
        self.assertEqual(enriched[0]["status"], "unresolved")

    def test_does_not_promote_link_to_truth_status(self):
        claims = [
            {
                "id": "claim_2",
                "text": "USNI News reported that delivery is not expected until 2034.",
                "status": "unresolved",
                "confidence": 0.45,
                "why_flagged": ["contains an attributed or externally verifiable assertion"],
                "evidence": [],
            }
        ]
        blocks = [
            ArticleBlock(
                text="USNI News reported that delivery is not expected until 2034.",
                links=[ArticleLink(text="USNI News", url="https://news.usni.org/example")],
            )
        ]

        enriched = attach_source_link_evidence(claims, blocks, "https://www.cnn.com/example")
        self.assertEqual(enriched[0]["status"], "unresolved")
        self.assertEqual(enriched[0]["evidence"][0]["kind"], "secondary")

    def test_ignores_social_share_link(self):
        claims = [
            {
                "id": "claim_3",
                "text": "Officials said the project would finish in 2027.",
                "status": "unresolved",
                "confidence": 0.35,
                "why_flagged": ["contains an attributed or externally verifiable assertion"],
                "evidence": [],
            }
        ]
        blocks = [
            ArticleBlock(
                text="Officials said the project would finish in 2027.",
                links=[ArticleLink(text="Share", url="https://x.com/intent/post")],
            )
        ]

        enriched = attach_source_link_evidence(claims, blocks, "https://example.com/story")
        self.assertEqual(enriched[0]["evidence"], [])


if __name__ == "__main__":
    unittest.main()
