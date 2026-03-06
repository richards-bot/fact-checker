import unittest

from poc_factcheck_timeline import extract_claims_heuristic
from poc_v2_factcheck_service import extract_claims, format_iconik_comment_payload, Claim


class FactCheckerTests(unittest.TestCase):
    def test_extract_claims_heuristic_finds_numeric_claim(self):
        lines = ["[00:00:03] Data shows emissions increased by 12 percent in 2025."]
        comments = extract_claims_heuristic(lines)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].risk, "low")

    def test_extract_claims_v2_finds_high_risk_claim(self):
        transcript = "[00:00:10] Three people were killed in the incident."
        claims = extract_claims(transcript)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].risk, "high")

    def test_format_payload_summary_counts(self):
        verifications = [
            {
                "claim": {"timecode": "00:00:01", "text": "Example", "risk": "high"},
                "verification_status": "needs_review",
                "search_hits": [],
                "confidence": 0.84,
                "suggested_action": "human_editor_review",
            }
        ]
        payload = format_iconik_comment_payload("asset-1", verifications)
        self.assertEqual(payload["factcheck_summary"]["claims_found"], 1)
        self.assertEqual(payload["factcheck_summary"]["high_risk"], 1)
        self.assertEqual(payload["factcheck_summary"]["needs_review"], 1)


if __name__ == "__main__":
    unittest.main()
