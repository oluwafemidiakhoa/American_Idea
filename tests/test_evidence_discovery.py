import unittest
from unittest.mock import patch

from app.services.evidence_discovery import (
    DiscoveryLead,
    build_discovery_queries,
    discover_evidence_for_claim,
)


class EvidenceDiscoveryTests(unittest.TestCase):
    def test_queries_are_short_transparent_and_repeatable(self):
        claim = "The Navy said the carrier is not expected to be delivered until 2034."
        first = build_discovery_queries(claim)
        second = build_discovery_queries(claim)
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 1)
        self.assertLessEqual(len(first), 3)
        self.assertTrue(any("2034" in query for query in first))
        self.assertTrue(all(len(query) < 220 for query in first))

    def test_discovery_deduplicates_same_url_across_providers(self):
        duplicate_url = "https://example.gov/document"
        federal = [
            DiscoveryLead(
                provider="federal_register",
                kind="primary",
                title="Official document",
                url=duplicate_url,
                source_name="Agency",
            )
        ]
        gdelt = [
            DiscoveryLead(
                provider="gdelt",
                kind="secondary",
                title="Republished document",
                url=duplicate_url,
                source_name="example.gov",
            ),
            DiscoveryLead(
                provider="gdelt",
                kind="secondary",
                title="Independent report",
                url="https://example.org/report",
                source_name="example.org",
            ),
        ]
        with patch("app.services.evidence_discovery.discover_federal_register", return_value=federal), patch(
            "app.services.evidence_discovery.discover_gdelt", return_value=gdelt
        ):
            result = discover_evidence_for_claim("Agency announced a program change in 2026.")

        urls = [lead["url"] for lead in result["leads"]]
        self.assertEqual(urls.count(duplicate_url), 1)
        self.assertIn("https://example.org/report", urls)
        self.assertEqual(result["leads"][0]["kind"], "primary")

    def test_discovery_does_not_assign_truth_relation(self):
        lead = DiscoveryLead(
            provider="gdelt",
            kind="secondary",
            title="Coverage",
            url="https://example.org/story",
        )
        with patch("app.services.evidence_discovery.discover_federal_register", return_value=[]), patch(
            "app.services.evidence_discovery.discover_gdelt", return_value=[lead]
        ):
            result = discover_evidence_for_claim("Officials reported 120 cases in 2026.")

        self.assertNotIn("relation", result["leads"][0])
        self.assertIn("unverified", result["methodology_note"].lower())


if __name__ == "__main__":
    unittest.main()
