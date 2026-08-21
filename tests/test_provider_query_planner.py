import unittest

from app.services.provider_query_planner import build_provider_query_plan


class ProviderQueryPlannerTests(unittest.TestCase):
    def test_life_science_queries_are_compact_and_entity_centered(self):
        claim = (
            "Merck and Moderna said on Wednesday their vaccine helped prevent the return and spread of disease "
            "in a large trial involving more than 1,000 melanoma patients."
        )
        anchors = ["Merck", "Moderna", "melanoma", "V940", "mRNA-4157", "Keytruda"]
        plan = build_provider_query_plan(
            claim,
            profile_name="life_science",
            retrieval_anchors=anchors,
        )

        self.assertTrue(plan["clinicaltrials_gov"])
        self.assertTrue(plan["pubmed"])
        self.assertTrue(plan["gdelt"])

        all_queries = [q for values in plan.values() for q in values]
        self.assertTrue(any("Moderna" in q or "Merck" in q for q in all_queries))
        self.assertTrue(any("melanoma" in q.lower() for q in all_queries))
        self.assertTrue(any("V940" in q or "mRNA-4157" in q for q in all_queries))
        self.assertTrue(all(len(q.split()) <= 8 for q in all_queries if q))
        self.assertTrue(all("Story title" not in q for q in all_queries))
        self.assertTrue(all("Wednesday" not in q for q in all_queries))

    def test_general_news_keeps_generic_fallback_queries(self):
        plan = build_provider_query_plan(
            "City officials reported that bridge repairs will begin in October.",
            profile_name="general",
            retrieval_anchors=["City officials", "bridge repairs", "October"],
        )
        self.assertTrue(plan["gdelt"])
        self.assertTrue(all(len(q.split()) <= 8 for q in plan["gdelt"] if q))


if __name__ == "__main__":
    unittest.main()
