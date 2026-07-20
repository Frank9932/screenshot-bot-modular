"""Contract tests for screenshot_store.store.ScreenshotStore -- the module that persists
already-captured PNG bytes under a caller-chosen key path (see
docs/agents/storage-reply-mvp-handoff.md for the full documented contract). No real WeChat/
Chrome/network involved anywhere in this file -- everything runs against a temp directory."""

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from screenshot_bot.screenshot_store import ScreenshotStore
from screenshot_bot.screenshot_store.store import _build_filename, _dedupe_path


class ScreenshotStoreTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.base_dir = Path(self._tmpdir.name) / "storage"
        self.store = ScreenshotStore(base_dir=self.base_dir)

    def test_successful_save_writes_bytes_and_returns_record(self):
        record = self.store.save_screenshot("user-1/channel_1/original", b"fake-png-bytes", duration_ms=42)

        self.assertTrue(record.file_path.exists())
        self.assertEqual(record.file_path.read_bytes(), b"fake-png-bytes")
        self.assertEqual(record.tab_name, "user-1/channel_1/original")
        self.assertEqual(record.duration_ms, 42)
        self.assertEqual(record.size_bytes, len(b"fake-png-bytes"))
        self.assertIsInstance(record.created_at, datetime)

    def test_missing_destination_directory_is_created_automatically(self):
        # base_dir itself doesn't exist yet -- nor does the multi-segment key underneath it.
        self.assertFalse(self.base_dir.exists())

        record = self.store.save_screenshot("brand-new-user/channel_9/original", b"bytes", duration_ms=1)

        self.assertTrue(record.file_path.parent.is_dir())
        self.assertEqual(record.file_path.parent, self.base_dir / "brand-new-user/channel_9/original")

    def test_duplicate_filename_does_not_overwrite_prior_save(self):
        # Force two saves to resolve to the identical base filename (same second, same
        # microsecond-derived timestamp, same duration_ms) -- the realistic trigger is two
        # rapid re-sends/re-captures landing in the same millisecond.
        fixed_time = datetime(2026, 7, 20, 10, 0, 0, 123000)
        with patch("screenshot_bot.screenshot_store.store.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_time
            first = self.store.save_screenshot("user-1/channel_1/original", b"first-bytes", duration_ms=50)
            second = self.store.save_screenshot("user-1/channel_1/original", b"second-bytes", duration_ms=50)

        self.assertNotEqual(first.file_path, second.file_path)
        self.assertTrue(first.file_path.exists())
        self.assertTrue(second.file_path.exists())
        self.assertEqual(first.file_path.read_bytes(), b"first-bytes")
        self.assertEqual(second.file_path.read_bytes(), b"second-bytes")

    def test_dedupe_path_appends_incrementing_counter(self):
        target = self.base_dir / "chan" / "20260720_100000_123_50ms.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"one")
        (self.base_dir / "chan" / "20260720_100000_123_50ms-1.png").write_bytes(b"two")

        deduped = _dedupe_path(target)

        self.assertEqual(deduped.name, "20260720_100000_123_50ms-2.png")
        self.assertFalse(deduped.exists())

    def test_invalid_image_source_raises_instead_of_silently_writing_garbage(self):
        with self.assertRaises(TypeError):
            self.store.save_screenshot("user-1/channel_1/original", None, duration_ms=1)

    def test_write_permission_failure_propagates_and_leaves_no_partial_record(self):
        with patch.object(Path, "write_bytes", side_effect=PermissionError("Access is denied")):
            with self.assertRaises(PermissionError):
                self.store.save_screenshot("user-1/channel_1/original", b"bytes", duration_ms=1)

        # The directory may exist (mkdir happens first) but no file should have been left behind.
        tab_dir = self.base_dir / "user-1/channel_1/original"
        if tab_dir.exists():
            self.assertEqual(list(tab_dir.iterdir()), [])

    def test_user_and_channel_paths_are_isolated_from_each_other(self):
        record_a = self.store.save_screenshot("user-a/channel_1/original", b"a-bytes", duration_ms=1)
        record_b = self.store.save_screenshot("user-b/channel_1/original", b"b-bytes", duration_ms=1)
        record_c = self.store.save_screenshot("user-a/channel_2/original", b"c-bytes", duration_ms=1)

        self.assertNotEqual(record_a.file_path.parent, record_b.file_path.parent)
        self.assertNotEqual(record_a.file_path.parent, record_c.file_path.parent)
        self.assertEqual(record_a.file_path.read_bytes(), b"a-bytes")
        self.assertEqual(record_b.file_path.read_bytes(), b"b-bytes")
        self.assertEqual(record_c.file_path.read_bytes(), b"c-bytes")
        # user-b's tree must not contain anything from user-a.
        user_b_root = self.base_dir / "user-b"
        all_files = [p for p in user_b_root.rglob("*") if p.is_file()]
        self.assertEqual(len(all_files), 1)

    def test_build_filename_embeds_timestamp_and_duration(self):
        captured_at = datetime(2026, 7, 20, 10, 0, 0, 123000)
        self.assertEqual(_build_filename(captured_at, 84), "20260720_100000_123_84ms.png")

    def test_no_metadata_sidecar_file_is_written(self):
        # ScreenshotStore has no metadata-file behavior today -- only the PNG itself is written,
        # and ScreenshotRecord is an in-memory return value only. Pinned explicitly so a future
        # change to add metadata persistence is a deliberate decision, not an accidental gap.
        record = self.store.save_screenshot("user-1/channel_1/original", b"bytes", duration_ms=1)

        siblings = list(record.file_path.parent.iterdir())
        self.assertEqual(siblings, [record.file_path])


if __name__ == "__main__":
    unittest.main()
