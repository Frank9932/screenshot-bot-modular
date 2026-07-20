"""Pure message-routing logic for the WeChat human-interaction layer.

Given an incoming message plus the sender's already-known state (their current channel, and
whether they've unlocked the private channel), `route_message` decides WHAT should happen next
-- it never sends anything, captures anything, or touches a file. That means it can be tested or
debugged completely standalone: no WeChat API, no browser, no config, no secrets, no running
webhook. `wechat_image_reply.WeChatImageReplyWorkflow` is the thin execution layer on top of this
that turns a decision into actual side effects (sending text, capturing a screenshot, persisting
channel/unlock state).

Run this file directly for an interactive REPL that exercises just this layer:
    python -m screenshot_bot.workflow.message_router
"""

from .equipment_prompts import (
    EQUIPMENT_CANCEL_WORDS,
    EQUIPMENT_CAPTURE_WORDS,
    EQUIPMENT_CONFIRM_WORDS,
    EQUIPMENT_START_WORDS,
)
from .help_text import GENERAL_HELP_WORDS, PRIVATE_CHANNEL_PASSCODE, PRIVATE_CHANNEL_WORDS
from .user_team_tracker import PRIVATE_CHANNEL_ID, UNASSIGNED
from .watermark_commands import parse_watermark_command

# Every `route_message` result is a dict with a "kind" key. The kinds and their extra fields:
#   general_help                    -- send the general help text
#   unlock_private                  -- persist the private-channel unlock, confirm it
#   join_private                    -- persist PRIVATE_CHANNEL_ID as the sender's channel, confirm
#   watermark_command  {command}    -- hand the already-parsed command dict to the watermark handler
#   private_photo                   -- sender is in the private channel; photo is archive-only
#   unassigned_photo_prompt         -- photo from a sender with no channel yet
#   join_channel  {channel_id, is_first_join} -- text digit: persist channel, then capture it
#   recapture     {channel_id}      -- photo from a sender with an assigned channel: capture it
#   guidance                        -- unrecognized text/message, fall back to plain-language help
#   ignored       {reason}          -- silently drop (configured ignore_message_types)
#
# Select-equipment guided flow (category -> equipment -> confirm -> capture; see
# equipment_prompts.py for the trigger words and equipment_selection_tracker.py for the
# persisted per-sender stage that `equipment_stage` below comes from):
#   equipment_start                              -- "设备": (re)start the flow, list categories
#   equipment_category_selected {category}       -- valid digit while awaiting_category
#   equipment_selected {category, equipment, path} -- valid digit while awaiting_equipment; carries
#                                                     the full selection so the caller never needs
#                                                     to re-derive `category` from equipment_stage
#   equipment_invalid_selection {stage}           -- anything other than a valid in-range digit
#                                                     (out-of-range digit, or non-numeric text)
#                                                     during either awaiting_* stage -- re-prompts
#                                                     the same list rather than falling through
#   equipment_confirmed                           -- "确认" while awaiting_confirm
#   equipment_cancelled                           -- "取消"/"cancel" while any equipment stage is
#                                                     active (awaiting_category, awaiting_equipment,
#                                                     awaiting_confirm, or confirmed) -- lets a
#                                                     sender back out of the flow at any point, not
#                                                     just right before confirming
#   equipment_capture {channel_id, category, equipment, path} -- "获取截图"/tap with a confirmed
#                                                     selection and a joined channel: go capture it
#   equipment_capture_not_ready                   -- "获取截图" with no confirmed selection yet
#   equipment_capture_no_channel                  -- confirmed selection, but sender hasn't joined
#                                                     a channel (equipment capture reuses that tab)


def route_message(
    msg_type,
    content,
    channel_id,
    private_unlocked,
    all_channel_ids,
    ignore_message_types,
    equipment_catalog_enabled=False,
    equipment_stage=None,
    equipment_categories=None,
    equipment_items=None,
):
    """
    msg_type/content: straight from the parsed WeChat message.
    channel_id: this sender's currently persisted channel (UNASSIGNED, PRIVATE_CHANNEL_ID, or a
        real channel id) -- the caller already looked this up via UserTeamTracker.
    private_unlocked: whether this sender has already sent the private-channel passcode.
    all_channel_ids: every configured channel id (including backup ones) -- a bare digit
        matching one of these joins/re-captures that channel.
    ignore_message_types: message types silently ignored when there's no channel to capture for.
    equipment_catalog_enabled: whether the select-equipment flow is configured at all -- when
        False, "设备"/"获取截图"/etc. are inert and fall through to ordinary guidance like any
        other text, same as PRIVATE_CHANNEL_WORDS staying inert until unlocked. Without this
        gate those words would be silently reserved (and equipment_capture_not_ready-style
        replies sent) even for deployments that never configured an equipment catalog.
    equipment_stage: this sender's current EquipmentSelectionTracker entry ({} if they've never
        started the select-equipment flow) -- e.g. {"stage": "awaiting_equipment", "category": "X"}.
    equipment_categories/equipment_items: the caller's already-loaded (from the equipment CSV)
        category list / current-category equipment list -- reading the CSV is I/O, so this
        function stays pure by having the caller fetch them ahead of time, same as all_channel_ids.
    """
    equipment_stage = equipment_stage or {}
    stage = equipment_stage.get("stage")

    if msg_type == "text":
        text = content.strip()
        text_lower = text.lower()

        if text_lower in GENERAL_HELP_WORDS:
            return {"kind": "general_help"}

        if text == PRIVATE_CHANNEL_PASSCODE:
            return {"kind": "unlock_private"}

        # "私密"/"private" is otherwise inert -- it only means anything for a sender who has
        # already unlocked it with the passcode above. An un-unlocked sender falls straight
        # through to the other checks (and eventually guidance), so the private channel stays
        # undiscoverable without the passcode.
        if text_lower in PRIVATE_CHANNEL_WORDS and private_unlocked:
            return {"kind": "join_private"}

        watermark_command = parse_watermark_command(content)
        if watermark_command is not None:
            return {"kind": "watermark_command", "command": watermark_command}

        # Every equipment-flow check below is gated on equipment_catalog_enabled -- when a
        # deployment never configured an equipment catalog, "设备"/"获取截图"/"确认"/"取消" are
        # completely inert and fall straight through to the channel-digit/guidance checks below,
        # same as PRIVATE_CHANNEL_WORDS staying inert until unlocked.
        if equipment_catalog_enabled:
            if text_lower in EQUIPMENT_START_WORDS:
                return {"kind": "equipment_start"}

            if text_lower in EQUIPMENT_CAPTURE_WORDS:
                if stage != "confirmed":
                    return {"kind": "equipment_capture_not_ready"}
                if channel_id in (UNASSIGNED, PRIVATE_CHANNEL_ID):
                    return {"kind": "equipment_capture_no_channel"}
                return {
                    "kind": "equipment_capture",
                    "channel_id": channel_id,
                    "category": equipment_stage.get("category", ""),
                    "equipment": equipment_stage.get("equipment", ""),
                    "path": equipment_stage.get("path", ""),
                }

            # "取消" backs out of any active equipment stage -- not just a pending confirm --
            # so a sender can abandon a category/equipment pick, or undo a confirm before
            # capturing, without needing to restart the whole flow via "设备". Checked before
            # the "确认" check and before the awaiting_category/awaiting_equipment catch-all
            # below so it always wins over both.
            if stage in ("awaiting_category", "awaiting_equipment", "awaiting_confirm", "confirmed"):
                if text_lower in EQUIPMENT_CANCEL_WORDS:
                    return {"kind": "equipment_cancelled"}

            # "确认" only means anything while a confirm is actually pending -- outside that
            # stage it falls through to guidance (or the catch-all below) like any other
            # unrecognized text.
            if stage == "awaiting_confirm" and text_lower in EQUIPMENT_CONFIRM_WORDS:
                return {"kind": "equipment_confirmed"}

            # While a category/equipment pick is actually pending, every other message is
            # treated as a list-index attempt -- a valid digit, an out-of-range digit, or
            # non-numeric noise are all "invalid selection" except the valid case, and none of
            # them ever falls through to the channel-join check below. Without this, a sender
            # mid-flow who sends a stray digit would silently switch channels, and one who
            # sends anything else would land on disconnected guidance text instead of being
            # re-prompted with the list they were already looking at.
            if stage == "awaiting_category":
                categories = equipment_categories or []
                if text.isdigit():
                    index = int(text) - 1
                    if 0 <= index < len(categories):
                        return {"kind": "equipment_category_selected", "category": categories[index]}
                return {"kind": "equipment_invalid_selection", "stage": stage}

            if stage == "awaiting_equipment":
                items = equipment_items or []
                if text.isdigit():
                    index = int(text) - 1
                    if 0 <= index < len(items):
                        item = items[index]
                        return {
                            "kind": "equipment_selected",
                            "category": equipment_stage.get("category", ""),
                            "equipment": item["equipment"],
                            "path": item["path"],
                        }
                return {"kind": "equipment_invalid_selection", "stage": stage}

        if text in all_channel_ids:
            return {"kind": "join_channel", "channel_id": text, "is_first_join": channel_id == UNASSIGNED}

    if msg_type == "image":
        # The private channel only archives what the sender uploads -- there is no
        # browser_targets entry backing it, so it can't be captured.
        if channel_id == PRIVATE_CHANNEL_ID:
            return {"kind": "private_photo"}
        # A photo carries no channel of its own -- if this sender has never picked one (no
        # prior digit message), there is nothing to capture for them yet.
        if channel_id == UNASSIGNED:
            return {"kind": "unassigned_photo_prompt"}
        return {"kind": "recapture", "channel_id": channel_id}

    if msg_type in ignore_message_types:
        return {"kind": "ignored", "reason": "message_type_disabled"}

    # Nothing above recognized this as a command or capture trigger.
    return {"kind": "guidance"}


def _repl():
    """Interactive standalone debugger for this module only -- no other capability module,
    config file, or secret is loaded. State is kept in memory for the duration of the REPL so
    you can walk through a multi-message conversation (e.g. send the passcode, then "私密")."""
    print("message_router REPL -- type a message; Ctrl+C to exit.")
    print("Commands: ':image' queues the next input as an image message instead of text.")
    print("          ':channels 1,2,3' sets the configured channel ids (default 1-5).")
    print("          ':ignore image' sets ignore_message_types (default 'image').")
    print("          ':equipment_enabled on|off' toggles equipment_catalog_enabled (default off, matching config default).")
    print("          ':equipment_categories A,B,C' sets the equipment CSV's category list (default empty).")
    print("          ':equipment_items name1:path1,name2:path2' sets the current category's equipment (default empty).")
    channel_id = UNASSIGNED
    private_unlocked = False
    all_channel_ids = {"1", "2", "3", "4", "5"}
    ignore_message_types = {"image"}
    equipment_catalog_enabled = False
    equipment_categories = []
    equipment_items = []
    equipment_stage = {}
    next_is_image = False
    while True:
        try:
            line = input(
                f"[channel={channel_id} private_unlocked={private_unlocked} "
                f"equipment_enabled={equipment_catalog_enabled} equipment_stage={equipment_stage.get('stage')}] > "
            )
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.startswith(":channels "):
            all_channel_ids = {c.strip() for c in line[len(":channels "):].split(",") if c.strip()}
            print("channels set to", sorted(all_channel_ids))
            continue
        if line.startswith(":ignore "):
            ignore_message_types = {c.strip() for c in line[len(":ignore "):].split(",") if c.strip()}
            print("ignore_message_types set to", sorted(ignore_message_types))
            continue
        if line.startswith(":equipment_enabled "):
            equipment_catalog_enabled = line[len(":equipment_enabled "):].strip().lower() in ("on", "true", "1", "yes")
            print("equipment_catalog_enabled set to", equipment_catalog_enabled)
            continue
        if line.startswith(":equipment_categories "):
            equipment_categories = [c.strip() for c in line[len(":equipment_categories "):].split(",") if c.strip()]
            print("equipment_categories set to", equipment_categories)
            continue
        if line.startswith(":equipment_items "):
            equipment_items = []
            for item in line[len(":equipment_items "):].split(","):
                item = item.strip()
                if not item:
                    continue
                name, _, path = item.partition(":")
                equipment_items.append({"equipment": name.strip(), "path": path.strip()})
            print("equipment_items set to", equipment_items)
            continue
        if line.strip() == ":image":
            next_is_image = True
            print("next message will be treated as an image")
            continue

        msg_type = "image" if next_is_image else "text"
        next_is_image = False
        action = route_message(
            msg_type, line, channel_id, private_unlocked, all_channel_ids, ignore_message_types,
            equipment_catalog_enabled=equipment_catalog_enabled,
            equipment_stage=equipment_stage, equipment_categories=equipment_categories, equipment_items=equipment_items,
        )
        print("->", action)

        # Mirror the state changes the real workflow would make, so the REPL stays coherent
        # across a multi-message conversation.
        if action["kind"] == "unlock_private":
            private_unlocked = True
        elif action["kind"] == "join_private":
            channel_id = PRIVATE_CHANNEL_ID
        elif action["kind"] == "join_channel":
            channel_id = action["channel_id"]
        elif action["kind"] == "equipment_start":
            equipment_stage = {"stage": "awaiting_category"}
        elif action["kind"] == "equipment_category_selected":
            equipment_stage = {"stage": "awaiting_equipment", "category": action["category"]}
            print("  (now use :equipment_items to set this category's equipment list)")
        elif action["kind"] == "equipment_selected":
            equipment_stage = {
                "stage": "awaiting_confirm",
                "category": action["category"],
                "equipment": action["equipment"],
                "path": action["path"],
            }
        elif action["kind"] == "equipment_confirmed":
            equipment_stage["stage"] = "confirmed"
        elif action["kind"] == "equipment_cancelled":
            equipment_stage = {}


if __name__ == "__main__":
    _repl()
