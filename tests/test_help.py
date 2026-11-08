"""Pure checks for the complete offline help catalog and search behavior."""
import unittest

from macro_help import BY_ID, CATEGORIES, TOPICS, search_topics
from macro_qt_workflow import KINDS


class HelpCatalogTests(unittest.TestCase):
    def test_all_current_palette_actions_have_a_dedicated_topic(self):
        missing = {kind for _, kind in KINDS
                   if f"action-{kind}" not in BY_ID}
        self.assertEqual(missing, set(), f"Missing help for: {missing}")

    def test_stable_ids_and_categories_are_unique(self):
        self.assertEqual(len(BY_ID), len(TOPICS))
        self.assertEqual(len({topic.id for topic in TOPICS}), len(TOPICS))
        self.assertTrue(CATEGORIES)
        for topic in TOPICS:
            with self.subTest(topic=topic.id):
                self.assertTrue(topic.id.strip())
                self.assertIn(topic.category, CATEGORIES)
                self.assertTrue(topic.title.strip())
                self.assertGreater(len(topic.body.strip()), 100)

    def test_debug_terms_find_plain_language_explanations(self):
        self.assertEqual(search_topics("debug gap")[0].id, "debug-gap")
        self.assertEqual(search_topics("breakpoint")[0].id, "breakpoint")
        self.assertEqual(search_topics("F9")[0].id, "breakpoint")
        self.assertEqual(search_topics("run from selected")[0].id,
                         "run-selected")
        self.assertEqual(search_topics("tesseract")[0].id, "ocr")

    def test_search_is_case_insensitive_and_uses_all_words(self):
        first = search_topics("BREAKPOINT")
        self.assertEqual(first, search_topics("breakpoint"))
        self.assertTrue(all(
            "breakpoint" in
            (topic.title + topic.keywords + topic.body).casefold()
            for topic in first))
        self.assertEqual(search_topics("impossiblezozzoterm"), [])

    def test_everyday_questions_ignore_punctuation_and_filler(self):
        self.assertEqual(search_topics("What does breakpoint mean?")[0].id,
                         "breakpoint")
        self.assertEqual(search_topics("Where is the debug gap?")[0].id,
                         "debug-gap")
        self.assertIn("action-click_image",
                      {topic.id for topic in search_topics("CLICK IMAGE!")})
        self.assertEqual(search_topics("!!!"), list(TOPICS))

    def test_category_filter_and_empty_search(self):
        categories = [topic for topic in TOPICS
                      if topic.category == "Action reference"]
        self.assertEqual(search_topics("", "Action reference"), categories)
        self.assertEqual(search_topics(), list(TOPICS))
        self.assertEqual(search_topics("", "All topics"), list(TOPICS))
        self.assertTrue(all(topic.category == "Running and debugging"
                            for topic in search_topics(
                                "debug", "Running and debugging")))
        with self.assertRaises(ValueError):
            search_topics("", "not a category")

    def test_everyday_descriptions_can_find_relevant_topics(self):
        for phrase, expected in (
            ("background window", "window-target"),
            ("clipboard", "action-clipboard_set"),
            ("save a workflow", "new-save-open"),
            ("slow down", "debug-gap"),
            ("restore unsaved", "recovery"),
        ):
            with self.subTest(phrase=phrase):
                ids = {topic.id for topic in search_topics(phrase)}
                self.assertIn(expected, ids)

    def test_offline_help_does_not_require_workflow_or_config(self):
        for topic in TOPICS:
            self.assertIsInstance(topic.body, str)
        self.assertIn("pauses before", BY_ID["breakpoint"].body)
        self.assertIn("between executable actions", BY_ID["debug-gap"].body)
        self.assertIn("1.0", BY_ID["debug-gap"].body)


if __name__ == "__main__":
    unittest.main()
