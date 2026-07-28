from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from help_content import HELP_TOPICS, filter_help_topics


class HelpContentTests(unittest.TestCase):
    def test_every_topic_has_a_title_and_a_non_trivial_body(self):
        self.assertGreater(len(HELP_TOPICS), 5)
        titles = [title for title, _body in HELP_TOPICS]
        self.assertEqual(len(titles), len(set(titles)), "topic titles must be unique")
        for title, body in HELP_TOPICS:
            self.assertGreater(len(title), 0)
            self.assertGreater(len(body), 40)

    def test_empty_query_returns_every_topic_in_original_order(self):
        self.assertEqual(filter_help_topics(HELP_TOPICS, ""), list(HELP_TOPICS))
        self.assertEqual(filter_help_topics(HELP_TOPICS, "   "), list(HELP_TOPICS))

    def test_search_is_case_insensitive_and_matches_the_tab_title(self):
        matches = filter_help_topics(HELP_TOPICS, "manual review")
        self.assertTrue(any("Manual review" in title for title, _body in matches))

    def test_search_matches_body_text_not_just_title(self):
        matches = filter_help_topics(HELP_TOPICS, "coherence")
        self.assertTrue(matches)
        for _title, body in matches:
            self.assertIn("coherence", body.lower())

    def test_multi_word_query_requires_every_word_present_in_any_order(self):
        matches = filter_help_topics(HELP_TOPICS, "mode close")
        self.assertTrue(any("Close modes" in title for title, _body in matches))

    def test_query_with_no_matches_returns_an_empty_list(self):
        self.assertEqual(filter_help_topics(HELP_TOPICS, "xyznotarealword"), [])


if __name__ == "__main__":
    unittest.main()
