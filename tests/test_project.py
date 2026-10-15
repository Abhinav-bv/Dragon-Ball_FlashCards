"""Offline tests for progression, persistence, locks, and playable user flows."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import api
import game
import storage

FIXTURES = [
    {"id": 1, "name": "Goku", "race": "Saiyan", "affiliation": "Z Fighter", "ki": "60.000.000", "image": "https://dragonball-api.com/characters/goku_normal.webp", "transformations": [{"name": "Goku SSJ", "ki": "3 Billion"}, {"name": "Goku final", "ki": "90 Septillion"}]},
    {"id": 2, "name": "Vegeta", "race": "Saiyan", "affiliation": "Z Fighter", "ki": "54.000.000", "transformations": []},
    {"id": 3, "name": "Bulma", "race": "Human", "affiliation": "Other", "ki": 0, "transformations": []},
]
QUESTION = {"mode": game.MODES[0], "prompt": "Who is this warrior?", "answer": "Goku", "options": ["Goku", "Vegeta"], "image": None, "hint": "Saiyan", "character": "Goku"}


class RulesTests(unittest.TestCase):
    def test_power_formats(self):
        self.assertEqual(game.power("60.000.000"), 60000000)
        self.assertEqual(game.power("19.84 Septillion"), game.Decimal('19.84e24'))
        self.assertEqual(game.power("1.8 Trillion"), game.Decimal('1.8e12'))
        self.assertIsNone(game.power("unknown"))
        self.assertIsNone(game.power("90 imaginary-units"))

    def test_rarity_milestones(self):
        self.assertEqual(game.rarity(0), "Common")
        self.assertEqual(game.rarity("3 Billion"), "Rare")
        self.assertEqual(game.rarity("90 Septillion"), "Mythic")
        self.assertEqual(game.requirement({"ki": "90 Septillion"}), 20)
        self.assertEqual(game.rarity(None), "Unranked")

    def test_all_quiz_modes_have_valid_choices(self):
        for mode in game.MODES:
            q = game.question(FIXTURES + [{**FIXTURES[1], "image": FIXTURES[0]["image"]}], mode)
            self.assertIn(q["answer"], q["options"])
            self.assertEqual(len(set(q["options"])), len(q["options"]))
            self.assertGreaterEqual(len(q["options"]), 2)

    def test_pagination_and_bad_data(self):
        with patch("api._get", side_effect=[{"items": [FIXTURES[1]], "meta": {"totalPages": 2}}, {"items": [FIXTURES[0], FIXTURES[1]], "meta": {"totalPages": 2}}]):
            self.assertEqual(len(api.get_characters()), 2)
        with patch("api._get", return_value={"items": "invalid"}):
            with self.assertRaises(api.DataError):
                api.get_characters()

    def test_vegeta_name_correction_and_zero(self):
        with patch("api._get", return_value={"id": 2, "name": "Vegeta", "transformations": [{"id": 11, "name": "old label"}]}):
            self.assertEqual(api.get_character(2)["transformations"][0]["name"], "Vegeta Ego")
        self.assertEqual(api.display_value(0), "0")


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(storage, "DB_PATH", Path(self.temp.name) / "save.sqlite3")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def win(self):
        ident = storage.new_round(QUESTION)
        storage.submit(ident, "Goku")
        return ident


class SaveTests(DatabaseCase):
    def test_welcome_pull_and_insufficient_tickets(self):
        self.assertEqual(storage.progress()["tickets"], 1)
        result = storage.pull(FIXTURES)
        self.assertIn(result["id"], storage.progress()["owned"])
        with self.assertRaises(ValueError):
            storage.pull(FIXTURES)
        self.assertEqual(storage.progress()["tickets"], 0)

    def test_rewards_are_idempotent(self):
        ident = self.win()
        self.assertFalse(storage.submit(ident, "Goku"))
        self.assertEqual(storage.progress()["wins"], 1)
        self.assertEqual(storage.progress()["tickets"], 2)

    def test_wrong_answer_cannot_be_changed_for_reward(self):
        ident = storage.new_round(QUESTION)
        storage.submit(ident, "Vegeta")
        self.assertFalse(storage.submit(ident, "Goku"))
        self.assertEqual(storage.progress()["wins"], 0)
        self.assertEqual(storage.get_round(ident)["submitted"], "Vegeta")

    def test_invalid_answer_preserves_round(self):
        ident = storage.new_round(QUESTION)
        with self.assertRaises(ValueError):
            storage.submit(ident, "not an option")
        self.assertIsNone(storage.get_round(ident)["won"])

    def test_no_duplicates_or_charge_when_complete(self):
        for _ in range(3):
            self.win()
        results = [storage.pull(FIXTURES)["id"] for _ in range(3)]
        self.assertEqual(len(set(results)), 3)
        before = storage.progress()["tickets"]
        with self.assertRaises(ValueError):
            storage.pull(FIXTURES)
        self.assertEqual(storage.progress()["tickets"], before)

    def test_progress_survives_new_database_connections(self):
        self.win()
        drawn = storage.pull(FIXTURES)
        state = storage.progress()
        self.assertEqual(state["wins"], 1)
        self.assertIn(drawn["id"], state["owned"])
        self.assertEqual(state["games"][0]["wins"], 1)


class AppTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        st.cache_data.clear()
        for mocker in [patch("api.get_characters", return_value=copy.deepcopy(FIXTURES)), patch("api.get_character", side_effect=lambda ident: copy.deepcopy(next(c for c in FIXTURES if c['id'] == ident)))]:
            mocker.start()
            self.addCleanup(mocker.stop)
        self.addCleanup(st.cache_data.clear)
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=10)

    def navigate(self, label):
        next(r for r in self.app.radio if r.label == "Go to").set_value(label).run()
        self.assertFalse(self.app.exception)

    def test_play_awards_once_across_reruns(self):
        with patch("game.question", return_value=QUESTION):
            self.app.run()
            self.app.button[0].click().run()
            next(r for r in self.app.radio if r.label == "Your answer").set_value("Goku").run()
            self.app.button[0].click().run()
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(storage.progress()["wins"], 1)
        self.assertEqual(self.app.metric[1].value, "2")

    def test_summon_and_comparison_lock(self):
        self.app.run()
        self.navigate("Summon")
        self.app.button[0].click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(storage.progress()["owned"]), 1)
        self.assertTrue(self.app.button[0].disabled)
        self.navigate("Compare")
        self.assertIn("at least two", self.app.info[0].value)

    def test_form_locked_then_unlocked_at_milestone(self):
        storage.pull([FIXTURES[0]])
        self.app.run()
        self.navigate("Collection")
        self.app.selectbox(key="collection_form_1").set_value(1).run()
        self.assertIn("3 more wins", self.app.warning[0].value)
        self.assertEqual(len(self.app.metric), 3)
        for _ in range(3):
            self.win()
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.metric[-1].value, "3 Billion")
        self.app.selectbox(key="collection_form_1").set_value(2).run()
        self.assertIn("17 more wins", self.app.warning[0].value)

    def test_service_outage_does_not_erase_progress(self):
        self.win()
        with patch("api.get_characters", side_effect=requests.Timeout()):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertIn("unavailable", self.app.error[0].value)
        self.assertEqual(storage.progress()["wins"], 1)


if __name__ == "__main__":
    unittest.main()
