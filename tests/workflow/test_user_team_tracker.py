"""Minimal unit tests for UserTeamTracker -- the last-seen channel + private-unlock fact
store that message_router.route_message consults for channel_id/private_unlocked."""

import tempfile
import unittest
from pathlib import Path

from screenshot_bot.workflow.user_team_tracker import PRIVATE_CHANNEL_ID, UNASSIGNED, UserTeamTracker


class UserTeamTrackerTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = Path(self._tmpdir.name) / "user-team-tracker.json"

    def tracker(self):
        return UserTeamTracker(self.path)

    def test_unknown_user_is_unassigned(self):
        self.assertEqual(self.tracker().get_team("user-1"), UNASSIGNED)

    def test_set_then_get_team(self):
        t = self.tracker()
        t.set_team("user-1", "3")
        self.assertEqual(t.get_team("user-1"), "3")

    def test_set_team_coerces_to_string(self):
        t = self.tracker()
        t.set_team("user-1", 3)
        self.assertEqual(t.get_team("user-1"), "3")

    def test_join_private_channel(self):
        t = self.tracker()
        t.set_team("user-1", PRIVATE_CHANNEL_ID)
        self.assertEqual(t.get_team("user-1"), PRIVATE_CHANNEL_ID)

    def test_unknown_user_has_not_unlocked_private(self):
        self.assertFalse(self.tracker().has_unlocked_private("user-1"))

    def test_unlock_private(self):
        t = self.tracker()
        t.unlock_private("user-1")
        self.assertTrue(t.has_unlocked_private("user-1"))

    def test_unlock_private_does_not_clobber_existing_team(self):
        t = self.tracker()
        t.set_team("user-1", "2")
        t.unlock_private("user-1")
        self.assertEqual(t.get_team("user-1"), "2")
        self.assertTrue(t.has_unlocked_private("user-1"))

    def test_set_team_does_not_clobber_existing_unlock(self):
        t = self.tracker()
        t.unlock_private("user-1")
        t.set_team("user-1", "2")
        self.assertTrue(t.has_unlocked_private("user-1"))
        self.assertEqual(t.get_team("user-1"), "2")

    def test_per_user_isolation(self):
        t = self.tracker()
        t.set_team("user-1", "1")
        t.set_team("user-2", "2")
        self.assertEqual(t.get_team("user-1"), "1")
        self.assertEqual(t.get_team("user-2"), "2")

    def test_persists_across_instances(self):
        self.tracker().set_team("user-1", "5")
        self.assertEqual(self.tracker().get_team("user-1"), "5")

    def test_corrupted_json_file_degrades_to_unassigned_not_a_crash(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(self.tracker().get_team("user-1"), UNASSIGNED)
        self.assertFalse(self.tracker().has_unlocked_private("user-1"))


if __name__ == "__main__":
    unittest.main()
