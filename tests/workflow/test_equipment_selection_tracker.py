"""Minimal unit tests for EquipmentSelectionTracker's persistence -- the per-sender stage
store that backs the select-equipment state machine tested in test_message_router.py."""

import tempfile
import unittest
from pathlib import Path

from screenshot_bot.workflow.equipment_selection_tracker import EquipmentSelectionTracker


class EquipmentSelectionTrackerTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = Path(self._tmpdir.name) / "equipment-selection-tracker.json"

    def tracker(self):
        return EquipmentSelectionTracker(self.path)

    def test_unknown_user_is_idle_empty_dict(self):
        self.assertEqual(self.tracker().get("user-1"), {})

    def test_start_sets_awaiting_category(self):
        t = self.tracker()
        t.start("user-1")
        self.assertEqual(t.get("user-1"), {"stage": "awaiting_category"})

    def test_set_category_sets_awaiting_equipment(self):
        t = self.tracker()
        t.set_category("user-1", "暖通设备")
        self.assertEqual(t.get("user-1"), {"stage": "awaiting_equipment", "category": "暖通设备"})

    def test_set_pending_equipment_sets_awaiting_confirm(self):
        t = self.tracker()
        t.set_pending_equipment("user-1", "暖通设备", "冷水机组1号", "hvac/chiller-1")
        self.assertEqual(
            t.get("user-1"),
            {"stage": "awaiting_confirm", "category": "暖通设备", "equipment": "冷水机组1号", "path": "hvac/chiller-1"},
        )

    def test_confirm_preserves_category_equipment_path(self):
        t = self.tracker()
        t.set_pending_equipment("user-1", "暖通设备", "冷水机组1号", "hvac/chiller-1")
        t.confirm("user-1")
        self.assertEqual(
            t.get("user-1"),
            {"stage": "confirmed", "category": "暖通设备", "equipment": "冷水机组1号", "path": "hvac/chiller-1"},
        )

    def test_confirm_with_no_prior_entry_still_sets_stage(self):
        # Defensive: confirm() on a user with no pending selection shouldn't raise.
        t = self.tracker()
        t.confirm("user-1")
        self.assertEqual(t.get("user-1"), {"stage": "confirmed"})

    def test_cancel_resets_to_the_same_state_as_never_started(self):
        # Regression: cancel() used to write {"stage": "none"}, a third state distinct from
        # both "never started" ({}) and every real awaiting_*/confirmed stage, even though no
        # caller ever branched on the literal string "none". Cancel must converge to Idle.
        t = self.tracker()
        t.start("user-1")
        t.set_category("user-1", "暖通设备")
        t.cancel("user-1")
        self.assertEqual(t.get("user-1"), self.tracker().get("never-started-user"))
        self.assertEqual(t.get("user-1"), {})

    def test_per_user_isolation(self):
        t = self.tracker()
        t.start("user-1")
        t.set_pending_equipment("user-2", "暖通设备", "X", "p")
        self.assertEqual(t.get("user-1"), {"stage": "awaiting_category"})
        self.assertEqual(t.get("user-2")["stage"], "awaiting_confirm")

    def test_persists_across_instances(self):
        self.tracker().start("user-1")
        reloaded = self.tracker().get("user-1")
        self.assertEqual(reloaded, {"stage": "awaiting_category"})

    def test_corrupted_json_file_degrades_to_idle_not_a_crash(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(self.tracker().get("user-1"), {})

    def test_json_file_containing_a_list_not_a_dict_degrades_to_idle(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(self.tracker().get("user-1"), {})


if __name__ == "__main__":
    unittest.main()
