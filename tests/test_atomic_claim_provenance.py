import unittest

from app.services.atomic_claims import compile_atomic_claims
from app.services.claim_extractor import extract_candidate_claims
from app.services.trust_gate import enforce_claim_trust


class AtomicClaimCompilerTests(unittest.TestCase):
    def test_taiwan_sentence_separates_quote_paraphrase_and_event(self):
        text = (
            "The appointed South Carolina senator said she 'tripped up' on a debate question "
            "about whether Taiwan is a US friend or foe"
        )
        compiled = compile_atomic_claims("claim_test", text)
        types = [item["atomic_type"] for item in compiled["atomic_claims"]]

        self.assertIn("attribution", types)
        self.assertIn("quote_fidelity", types)
        self.assertIn("paraphrase", types)
        self.assertIn("event_fact", types)
        self.assertIn("compound_claim", compiled["integrity_flags"])
        self.assertIn("quote_plus_publisher_paraphrase", compiled["integrity_flags"])

    def test_quote_fidelity_requires_source_of_record(self):
        compiled = compile_atomic_claims("claim_q", 'The senator said "Of course, Taiwan is our friend."')
        quote_atom = next(item for item in compiled["atomic_claims"] if item["atomic_type"] == "quote_fidelity")
        contract = quote_atom["evidence_contract"]
        self.assertEqual(contract["name"], "verbatim_or_faithful_quote")
        self.assertIn("source-of-record", contract["minimum"])

    def test_causal_claim_uses_stronger_contract(self):
        compiled = compile_atomic_claims("claim_c", "The policy caused unemployment to increase by 18% in 2026.")
        causal = next(item for item in compiled["atomic_claims"] if item["atomic_type"] == "causal_claim")
        self.assertEqual(causal["evidence_contract"]["name"], "causal_evidence")
        self.assertTrue(causal["evidence_contract"]["independent_corroboration_required"])

    def test_extractor_attaches_atomic_provenance(self):
        text = (
            "The governor said Tuesday that the program served 1,240,000 people in 2025. "
            "An independent audit found that processing time fell by 18%."
        )
        claims = extract_candidate_claims(text)
        self.assertTrue(claims)
        self.assertTrue(all("atomic_claims" in claim for claim in claims))
        self.assertTrue(all(claim["atomic_claim_count"] >= 1 for claim in claims))


class AtomicTrustGateTests(unittest.TestCase):
    def test_compound_parent_cannot_resolve_while_atoms_unresolved(self):
        compiled = compile_atomic_claims(
            "claim_test",
            "The senator said she 'tripped up' on a debate question about whether Taiwan is a US friend or foe",
        )
        claim = {
            "id": "claim_test",
            "text": compiled["source_sentence"],
            "status": "supported",
            "atomic_claims": compiled["atomic_claims"],
            "evidence": [
                {
                    "kind": "primary",
                    "relation": "supports",
                    "verification_confidence": 0.92,
                    "fetch_status": "verified",
                    "url": "https://primary.example/transcript",
                },
                {
                    "kind": "secondary",
                    "relation": "supports",
                    "verification_confidence": 0.90,
                    "fetch_status": "verified",
                    "url": "https://independent.example/report",
                },
            ],
        }
        enforced = enforce_claim_trust(claim)
        self.assertEqual(enforced["status"], "unresolved")
        self.assertGreater(enforced["trust_gate"]["unresolved_atomic_count"], 0)
        self.assertIn("Atomic Claim Provenance blocks parent resolution", enforced["status_basis"])

    def test_mixed_atomic_outcomes_produce_mixed_aggregate(self):
        claim = {
            "status": "unresolved",
            "evidence": [],
            "atomic_claims": [
                {"status": "supported"},
                {"status": "unsupported"},
            ],
        }
        enforced = enforce_claim_trust(claim)
        self.assertEqual(enforced["aggregate_status"], "mixed")


if __name__ == "__main__":
    unittest.main()
