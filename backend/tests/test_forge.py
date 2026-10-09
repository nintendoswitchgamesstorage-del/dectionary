"""Acceptance tests for the local, evidence-honest word-making engine."""

import copy
import unittest

from backend.forge import LEVELS, generate


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "concept": "power borrowed from another person's memory",
            "roots": [
                {"text": "borrow", "language": "English", "meaning": "take on loan"},
                {"text": "memory", "language": "English", "meaning": "a retained trace"},
                {"text": "power", "language": "English", "meaning": "capacity to act"},
            ],
            "level": "inventive",
            "count": 12,
            "seed": 14,
        }

    def test_repeatability_without_mutating_inputs(self):
        original = copy.deepcopy(self.payload)
        self.assertEqual(generate(self.payload), generate(self.payload))
        self.assertEqual(self.payload, original)
        implicit_seed = {key: value for key, value in self.payload.items() if key != "seed"}
        self.assertEqual(generate(implicit_seed), generate(implicit_seed))
        different = {**self.payload, "seed": 91}
        self.assertNotEqual([c["term"] for c in generate(different)], [c["term"] for c in generate(self.payload)])

    def test_revised_root_meanings_do_not_overwrite_a_saved_recipe_identity(self):
        first = {c["term"]: c for c in generate(self.payload)}
        revised_payload = copy.deepcopy(self.payload)
        revised_payload["roots"][0]["meaning"] = "adopt another person's authority"
        second = {c["term"]: c for c in generate(revised_payload)}
        shared = set(first) & set(second)
        changed = [term for term in shared if any(part["text"] == "borrow" for part in first[term]["components"])]
        self.assertTrue(changed)
        for term in changed:
            self.assertNotEqual(first[term]["id"], second[term]["id"])

    def test_all_levels_have_real_distinct_constructions(self):
        terms = {}
        for level in LEVELS:
            candidates = generate({**self.payload, "level": level})
            self.assertEqual(len(candidates), 12)
            self.assertGreaterEqual(len({c["technique"] for c in candidates}), 3)
            self.assertTrue(all(level in c["tags"] for c in candidates))
            terms[level] = {c["term"] for c in candidates}
        for left, right in zip(LEVELS, LEVELS[1:]):
            self.assertNotEqual(terms[left], terms[right])
        self.assertTrue(any("↯" in c["term"] or "∴" in c["term"] for c in generate({**self.payload, "level": "radical", "count": 30})))

    def test_provenance_never_promotes_generated_terms_to_attested(self):
        candidates = generate(self.payload)
        for candidate in candidates:
            self.assertEqual(candidate["evidence_status"], "coined")
            self.assertEqual(candidate["source_type"], "coined")
            self.assertEqual(candidate["source"], {"title": "Local Neologism Forge"})
            self.assertNotIn("url", candidate["source"])
            self.assertNotIn("page", candidate["source"])
            self.assertIn("prior use has not been checked", candidate["caveat"])
            self.assertIn("heuristic", candidate["fit_reason"])
            self.assertGreaterEqual(candidate["fit"], 0)
            self.assertLessEqual(candidate["fit"], 100)

    def test_cross_language_roots_keep_supplied_glosses_and_review_warning(self):
        payload = {
            "concept": "dreams moving through a sea of uncertainty",
            "roots": [
                {"text": "梦", "language": "Chinese", "meaning": "dream (supplied gloss)"},
                {"text": "θάλασσα", "language": "Greek", "meaning": "sea (supplied gloss)"},
            ],
            "count": 30,
            "level": "inventive",
        }
        candidates = generate(payload)
        hybrid = next(c for c in candidates if c["technique"] == "Cross-language splice")
        self.assertIn("Chinese", hybrid["language"])
        self.assertIn("Greek", hybrid["language"])
        self.assertEqual(hybrid["components"], payload["roots"] if hybrid["term"].startswith("梦") else list(reversed(payload["roots"])))
        self.assertIn("Native-speaker and grammar review", hybrid["caveat"])
        self.assertIn("not verified grammar", hybrid["caveat"])
        self.assertIn("supplied", hybrid["fit_reason"])

    def test_portmanteau_explanation_reports_real_fragments(self):
        candidates = generate({**self.payload, "count": 30})
        port = next(c for c in candidates if c["technique"] == "Portmanteau")
        a, b = port["components"]
        first = a["text"][: -(-len(a["text"]) * 6 // 10)]
        last_length = -(-len(b["text"]) * 6 // 10)
        last = b["text"][-last_length:]
        self.assertEqual(port["term"], first + last)
        self.assertIn("“" + first + "”", port["fit_reason"])
        self.assertIn("“" + last + "”", port["fit_reason"])
        self.assertIn("Clipping", port["misses"])

    def test_game_settings_are_not_presented_as_natural_languages(self):
        candidates = generate({
            "concept": "a world changed by the appetite of a creature",
            "roots": [
                {"text": "slime", "language": "Slime Rancher", "meaning": "a user-supplied game concept"},
                {"text": "bloom", "language": "English", "meaning": "growth"},
            ],
            "count": 30,
        })
        game_candidates = [c for c in candidates if any(p["language"] == "Slime Rancher" for p in c["components"])]
        self.assertTrue(game_candidates)
        for candidate in game_candidates:
            self.assertIn("source settings, not natural languages", candidate["caveat"])
            self.assertNotIn("review is needed for Slime Rancher", candidate["caveat"])

    def test_single_character_and_no_root_inputs_fill_requested_count(self):
        for level in LEVELS:
            for roots in ([], [{"text": "梦", "language": "Chinese", "meaning": "dream"}]):
                candidates = generate({"concept": "", "roots": roots, "level": level, "count": 30})
                self.assertEqual(len(candidates), 30, (level, roots))
                self.assertEqual(len({c["term"].casefold() for c in candidates}), 30)
                self.assertTrue(all(c["term"].strip() and len(c["term"]) <= 120 for c in candidates))

    def test_bounded_malformed_and_unicode_input(self):
        candidates = generate({
            "concept": "x" * 10000,
            "roots": [None, {"text": "\x00\n"}, {"text": "e\u0301" * 1000, "language": "French", "meaning": "y" * 1000}],
            "level": "unknown",
            "count": 100000,
        })
        self.assertEqual(len(candidates), 30)
        self.assertTrue(all("inventive" in c["tags"] for c in candidates))
        self.assertTrue(all(len(c["term"]) <= 120 for c in candidates))
        self.assertTrue(all(len(part["text"]) <= 48 for c in candidates for part in c["components"]))
        self.assertEqual(len(generate({"count": 0})), 1)
        self.assertEqual(len(generate({"count": "bad"})), 8)
        with self.assertRaises(ValueError):
            generate(None)


if __name__ == "__main__":
    unittest.main()
