"""Minimal unit tests for the equipment CSV reader that backs the category/equipment lists
in the select-equipment state machine."""

import csv
import tempfile
import unittest
from pathlib import Path

from screenshot_bot.workflow.equipment_catalog import load_categories, load_equipment


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "equipment", "path"])
        writer.writeheader()
        writer.writerows(rows)


class EquipmentCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.csv_path = Path(self._tmpdir.name) / "equipment.csv"

    def test_load_categories_preserves_first_seen_order_and_dedupes(self):
        write_csv(self.csv_path, [
            {"category": "暖通设备", "equipment": "A", "path": "a"},
            {"category": "配电设备", "equipment": "B", "path": "b"},
            {"category": "暖通设备", "equipment": "C", "path": "c"},
        ])
        self.assertEqual(load_categories(self.csv_path), ["暖通设备", "配电设备"])

    def test_load_categories_empty_file_no_candidates(self):
        write_csv(self.csv_path, [])
        self.assertEqual(load_categories(self.csv_path), [])

    def test_load_equipment_single_candidate(self):
        write_csv(self.csv_path, [{"category": "暖通设备", "equipment": "A", "path": "a"}])
        self.assertEqual(load_equipment(self.csv_path, "暖通设备"), [{"equipment": "A", "path": "a"}])

    def test_load_equipment_multiple_candidates_preserves_order(self):
        write_csv(self.csv_path, [
            {"category": "暖通设备", "equipment": "A", "path": "a"},
            {"category": "暖通设备", "equipment": "B", "path": "b"},
        ])
        self.assertEqual(
            load_equipment(self.csv_path, "暖通设备"),
            [{"equipment": "A", "path": "a"}, {"equipment": "B", "path": "b"}],
        )

    def test_load_equipment_unknown_category_no_candidates(self):
        write_csv(self.csv_path, [{"category": "暖通设备", "equipment": "A", "path": "a"}])
        self.assertEqual(load_equipment(self.csv_path, "不存在的类别"), [])

    def test_load_equipment_filters_out_other_categories(self):
        write_csv(self.csv_path, [
            {"category": "暖通设备", "equipment": "A", "path": "a"},
            {"category": "配电设备", "equipment": "B", "path": "b"},
        ])
        self.assertEqual(load_equipment(self.csv_path, "配电设备"), [{"equipment": "B", "path": "b"}])

    def test_missing_file_raises_oserror(self):
        missing_path = Path(self._tmpdir.name) / "does-not-exist.csv"
        with self.assertRaises(OSError):
            load_categories(missing_path)
        with self.assertRaises(OSError):
            load_equipment(missing_path, "暖通设备")


if __name__ == "__main__":
    unittest.main()
