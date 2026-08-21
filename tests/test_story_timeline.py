import unittest

from app.services.story_timeline import detect_correction_language, text_delta


class StoryTimelineTests(unittest.TestCase):
    def test_detects_explicit_correction_language(self):
        detected, excerpt = detect_correction_language(
            "Correction: An earlier version of this story misstated the year. The correct year is 2034."
        )
        self.assertTrue(detected)
        self.assertIn("Correction", excerpt)

    def test_does_not_call_ordinary_edit_a_correction(self):
        detected, excerpt = detect_correction_language(
            "The Navy said the carrier is expected to be delivered in 2034 after construction delays."
        )
        self.assertFalse(detected)
        self.assertIsNone(excerpt)

    def test_text_delta_reports_added_and_removed_passages(self):
        before = "The carrier is expected in 2031. Officials said construction remains on schedule."
        after = "The carrier is expected in 2034. Officials said construction remains delayed."
        delta = text_delta(before, after)
        self.assertTrue(delta["changed"])
        self.assertGreater(delta["added_count"], 0)
        self.assertGreater(delta["removed_count"], 0)
        self.assertLess(delta["similarity"], 1.0)

    def test_identical_text_is_not_changed(self):
        text = "The agency reported 1,200 cases in 2026."
        delta = text_delta(text, text)
        self.assertFalse(delta["changed"])
        self.assertEqual(delta["added_count"], 0)
        self.assertEqual(delta["removed_count"], 0)


if __name__ == "__main__":
    unittest.main()
