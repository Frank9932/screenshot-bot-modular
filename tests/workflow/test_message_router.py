"""Minimal unit tests for the pure `route_message` decision function -- covers the
select-equipment state machine (Idle -> Choose Category -> Choose Equipment -> Pending
Confirm -> Confirmed -> Capture) plus the channel/private/watermark decisions it shares
that state machine with. No I/O, no fixtures beyond plain dicts/sets -- matches
`route_message`'s own no-I/O design (see message_router.py's module docstring)."""

import unittest

from screenshot_bot.workflow.message_router import route_message
from screenshot_bot.workflow.user_team_tracker import PRIVATE_CHANNEL_ID, UNASSIGNED

CATEGORIES = ["暖通设备", "配电设备", "给排水设备"]
ITEMS = [
    {"equipment": "冷水机组1号", "path": "hvac/chiller-1"},
    {"equipment": "冷水机组2号", "path": "hvac/chiller-2"},
]
ALL_CHANNELS = {"1", "2", "3"}
IGNORE_TYPES = {"voice"}


def route(msg_type="text", content="", channel_id=UNASSIGNED, private_unlocked=False,
          all_channel_ids=ALL_CHANNELS, ignore_message_types=IGNORE_TYPES,
          equipment_catalog_enabled=True, equipment_stage=None,
          equipment_categories=None, equipment_items=None):
    return route_message(
        msg_type, content, channel_id, private_unlocked, all_channel_ids, ignore_message_types,
        equipment_catalog_enabled=equipment_catalog_enabled,
        equipment_stage=equipment_stage, equipment_categories=equipment_categories,
        equipment_items=equipment_items,
    )


class IdleStateTests(unittest.TestCase):
    def test_equipment_start_from_idle_no_stage(self):
        action = route(content="设备", equipment_stage=None)
        self.assertEqual(action, {"kind": "equipment_start"})

    def test_equipment_start_from_idle_empty_stage_dict(self):
        # {} (never started) must behave identically to None -- both are "no entry yet".
        action = route(content="设备", equipment_stage={})
        self.assertEqual(action, {"kind": "equipment_start"})

    def test_equipment_words_inert_when_catalog_disabled(self):
        # equipment_catalog_enabled=False: "设备" is not a channel id, so it falls to guidance.
        action = route(content="设备", equipment_catalog_enabled=False, equipment_stage=None)
        self.assertEqual(action, {"kind": "guidance"})

    def test_bare_digit_with_no_active_flow_is_channel_join_not_equipment_index(self):
        action = route(content="1", equipment_stage=None,
                        equipment_categories=CATEGORIES, equipment_items=ITEMS)
        self.assertEqual(action["kind"], "join_channel")
        self.assertEqual(action["channel_id"], "1")


class ChooseCategoryTests(unittest.TestCase):
    stage = {"stage": "awaiting_category"}

    def test_single_candidate_selected(self):
        action = route(content="1", equipment_stage=self.stage, equipment_categories=["暖通设备"])
        self.assertEqual(action, {"kind": "equipment_category_selected", "category": "暖通设备"})

    def test_multiple_candidates_selects_correct_index(self):
        action = route(content="2", equipment_stage=self.stage, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "equipment_category_selected", "category": "配电设备"})

    def test_no_candidates_any_digit_is_invalid_not_a_crash(self):
        action = route(content="1", equipment_stage=self.stage, equipment_categories=[])
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_category"})

    def test_illegal_index_out_of_range(self):
        action = route(content="99", equipment_stage=self.stage, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_category"})

    def test_illegal_index_zero(self):
        action = route(content="0", equipment_stage=self.stage, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_category"})

    def test_non_numeric_text_is_invalid_selection_not_generic_guidance(self):
        # Regression: previously fell straight through to "guidance", losing all context that
        # the sender was still mid category-pick.
        action = route(content="abc", equipment_stage=self.stage, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_category"})

    def test_restart_word_wins_over_awaiting_category(self):
        action = route(content="设备", equipment_stage=self.stage, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "equipment_start"})

    def test_cancel_from_awaiting_category(self):
        # Regression: cancel used to only work from awaiting_confirm.
        action = route(content="取消", equipment_stage=self.stage, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "equipment_cancelled"})


class ChooseEquipmentTests(unittest.TestCase):
    stage = {"stage": "awaiting_equipment", "category": "暖通设备"}

    def test_single_candidate_selected(self):
        action = route(content="1", equipment_stage=self.stage, equipment_items=[ITEMS[0]])
        self.assertEqual(
            action,
            {"kind": "equipment_selected", "category": "暖通设备", "equipment": "冷水机组1号", "path": "hvac/chiller-1"},
        )

    def test_multiple_candidates_selects_correct_index(self):
        action = route(content="2", equipment_stage=self.stage, equipment_items=ITEMS)
        self.assertEqual(
            action,
            {"kind": "equipment_selected", "category": "暖通设备", "equipment": "冷水机组2号", "path": "hvac/chiller-2"},
        )

    def test_no_candidates_any_digit_is_invalid(self):
        action = route(content="1", equipment_stage=self.stage, equipment_items=[])
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_equipment"})

    def test_illegal_index_out_of_range(self):
        action = route(content="99", equipment_stage=self.stage, equipment_items=ITEMS)
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_equipment"})

    def test_non_numeric_text_is_invalid_selection(self):
        action = route(content="不知道", equipment_stage=self.stage, equipment_items=ITEMS)
        self.assertEqual(action, {"kind": "equipment_invalid_selection", "stage": "awaiting_equipment"})

    def test_cancel_from_awaiting_equipment(self):
        action = route(content="cancel", equipment_stage=self.stage, equipment_items=ITEMS)
        self.assertEqual(action, {"kind": "equipment_cancelled"})

    def test_a_digit_never_falls_through_to_channel_join(self):
        # "1" is also a valid channel id, but mid-flow it must always resolve as list index.
        action = route(content="1", equipment_stage=self.stage, equipment_items=[])
        self.assertNotEqual(action["kind"], "join_channel")


class PendingConfirmTests(unittest.TestCase):
    stage = {"stage": "awaiting_confirm", "category": "暖通设备", "equipment": "冷水机组1号", "path": "hvac/chiller-1"}

    def test_confirm(self):
        action = route(content="确认", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "equipment_confirmed"})

    def test_confirm_english_word(self):
        action = route(content="confirm", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "equipment_confirmed"})

    def test_cancel(self):
        action = route(content="取消", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "equipment_cancelled"})

    def test_unrelated_text_falls_to_guidance(self):
        # awaiting_confirm has no "list" to re-prompt with, so unrecognized text should not be
        # forced into equipment_invalid_selection -- ordinary guidance is correct here.
        action = route(content="随便说点什么", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "guidance"})

    def test_digit_mid_confirm_is_channel_join_not_equipment_action(self):
        # Channel selection and equipment selection are orthogonal/parallel state -- a channel
        # digit sent while a confirm is pending should not be swallowed by the equipment flow.
        action = route(content="2", equipment_stage=self.stage)
        self.assertEqual(action["kind"], "join_channel")


class ConfirmedStateTests(unittest.TestCase):
    stage = {"stage": "confirmed", "category": "暖通设备", "equipment": "冷水机组1号", "path": "hvac/chiller-1"}

    def test_duplicate_confirm_does_not_crash_falls_to_guidance(self):
        # Documents current behavior: re-confirming an already-confirmed selection is not a
        # recognized action, so it degrades gracefully to guidance rather than erroring.
        action = route(content="确认", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "guidance"})

    def test_cancel_from_confirmed(self):
        # Regression: cancel used to only work from awaiting_confirm; a sender who confirmed
        # and then changed their mind had no way to back out except restarting via "设备".
        action = route(content="取消", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "equipment_cancelled"})

    def test_restart_still_wins_from_confirmed(self):
        action = route(content="设备", equipment_stage=self.stage)
        self.assertEqual(action, {"kind": "equipment_start"})


class CaptureTests(unittest.TestCase):
    confirmed_stage = {"stage": "confirmed", "category": "暖通设备", "equipment": "冷水机组1号", "path": "hvac/chiller-1"}

    def test_capture_not_ready_when_not_confirmed(self):
        for stage in (None, {}, {"stage": "awaiting_category"}, {"stage": "awaiting_confirm"}):
            with self.subTest(stage=stage):
                action = route(content="获取截图", channel_id="1", equipment_stage=stage)
                self.assertEqual(action, {"kind": "equipment_capture_not_ready"})

    def test_capture_no_channel_when_unassigned(self):
        action = route(content="截图", channel_id=UNASSIGNED, equipment_stage=self.confirmed_stage)
        self.assertEqual(action, {"kind": "equipment_capture_no_channel"})

    def test_capture_no_channel_when_private(self):
        action = route(content="截图", channel_id=PRIVATE_CHANNEL_ID, equipment_stage=self.confirmed_stage)
        self.assertEqual(action, {"kind": "equipment_capture_no_channel"})

    def test_capture_confirmed_with_channel(self):
        action = route(content="获取截图", channel_id="1", equipment_stage=self.confirmed_stage)
        self.assertEqual(
            action,
            {
                "kind": "equipment_capture",
                "channel_id": "1",
                "category": "暖通设备",
                "equipment": "冷水机组1号",
                "path": "hvac/chiller-1",
            },
        )


class LostOrMalformedStateTests(unittest.TestCase):
    def test_none_stage_treated_as_idle(self):
        action = route(content="1", equipment_stage=None)
        self.assertEqual(action["kind"], "join_channel")

    def test_empty_dict_stage_treated_as_idle(self):
        action = route(content="1", equipment_stage={})
        self.assertEqual(action["kind"], "join_channel")

    def test_entry_missing_stage_key_treated_as_idle(self):
        # Simulates a persisted entry that somehow lost its "stage" key -- should degrade to
        # Idle rather than raising or matching any awaiting_* branch.
        action = route(content="1", equipment_stage={"category": "暖通设备"})
        self.assertEqual(action["kind"], "join_channel")

    def test_unknown_stage_value_treated_as_idle(self):
        action = route(content="1", equipment_stage={"stage": "some_future_stage_this_version_does_not_know"})
        self.assertEqual(action["kind"], "join_channel")


class NoExpiryDocumentationTests(unittest.TestCase):
    """`route_message` takes no timestamp/TTL and `EquipmentSelectionTracker` stores no
    "last updated" field -- there is currently no state-expiry mechanism at all. A stage
    persisted arbitrarily long ago is treated exactly like one set a second ago. This is not a
    bug being fixed here (no requirement anywhere specifies a TTL); it's a known, deliberate
    gap -- see the handoff doc's "Known Risks" section. This test exists so a future change
    that *does* add expiry has something concrete to update."""

    def test_stale_looking_stage_is_still_treated_as_fully_active(self):
        stage = {"stage": "awaiting_confirm", "category": "暖通设备", "equipment": "老设备", "path": "x"}
        action = route(content="确认", equipment_stage=stage)
        self.assertEqual(action, {"kind": "equipment_confirmed"})


class PrecedenceTests(unittest.TestCase):
    """Equipment-flow words must never shadow the higher-precedence checks that run before
    them (general help, private-channel passcode, watermark commands)."""

    def test_general_help_wins_over_equipment_stage(self):
        action = route(content="帮助", equipment_stage={"stage": "awaiting_category"}, equipment_categories=CATEGORIES)
        self.assertEqual(action, {"kind": "general_help"})

    def test_watermark_command_wins_over_equipment_stage(self):
        action = route(content="水印 1 状态", equipment_stage={"stage": "awaiting_confirm"})
        self.assertEqual(action["kind"], "watermark_command")


class NonEquipmentRoutingStillWorksTests(unittest.TestCase):
    """Sanity checks that the equipment-flow changes didn't disturb the channel/private/image
    routing this module also owns."""

    def test_join_channel(self):
        action = route(content="2", equipment_stage=None)
        self.assertEqual(action, {"kind": "join_channel", "channel_id": "2", "is_first_join": True})

    def test_recapture_photo_with_assigned_channel(self):
        action = route(msg_type="image", channel_id="1", equipment_stage=None)
        self.assertEqual(action, {"kind": "recapture", "channel_id": "1"})

    def test_unassigned_photo_prompt(self):
        action = route(msg_type="image", channel_id=UNASSIGNED, equipment_stage=None)
        self.assertEqual(action, {"kind": "unassigned_photo_prompt"})

    def test_private_photo(self):
        action = route(msg_type="image", channel_id=PRIVATE_CHANNEL_ID, equipment_stage=None)
        self.assertEqual(action, {"kind": "private_photo"})

    def test_ignored_message_type(self):
        action = route(msg_type="voice", content="", equipment_stage=None)
        self.assertEqual(action, {"kind": "ignored", "reason": "message_type_disabled"})


if __name__ == "__main__":
    unittest.main()
