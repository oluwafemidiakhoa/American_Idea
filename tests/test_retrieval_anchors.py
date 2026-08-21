import unittest

from app.services.retrieval_anchors import build_anchor_query, extract_retrieval_anchors


class RetrievalAnchorTests(unittest.TestCase):
    def test_extracts_stable_life_science_identifiers(self):
        anchors = extract_retrieval_anchors(
            "Moderna and Merck studied V940, also known as mRNA-4157, with Keytruda in melanoma."
        )
        lowered = {item.lower() for item in anchors}
        self.assertIn("moderna", lowered)
        self.assertIn("merck", lowered)
        self.assertIn("v940", lowered)
        self.assertIn("mrna-4157", lowered)
        self.assertIn("keytruda", lowered)

    def test_context_can_supply_missing_entities_for_vague_quote(self):
        query = build_anchor_query(
            '“What we saw in the mid-stage trial were reactions similar to a flu or COVID shot,” Hoge said.',
            "Story title: Moderna, Merck breakthrough could usher in wave of cancer vaccines Nearby claim: Merck and Moderna tested V940 with Keytruda in melanoma.",
        )
        self.assertIn("Moderna", query)
        self.assertIn("Merck", query)
        self.assertIn("V940", query)
        self.assertIn("Keytruda", query)


if __name__ == "__main__":
    unittest.main()
